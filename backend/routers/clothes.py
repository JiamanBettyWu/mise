import logging
import traceback

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth import require_password

log = logging.getLogger("wardrobe.clothes")
from db.supabase import client as supabase
from schemas import ClothingItem, ClothingItemCreate, ClothingItemUpdate, TagSuggestion
from services.claude import tag_clothing_photo, tag_clothing_photo_multi
from services.image import crop_to_bbox, ensure_under_limit, fit_to_vision_limits
from services.storage import delete_photo, upload_photo

router = APIRouter(
    prefix="/clothes",
    tags=["clothes"],
    dependencies=[Depends(require_password)],
)

ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic"}


@router.post("/upload", response_model=TagSuggestion | list[TagSuggestion])
async def upload_and_tag(
    file: UploadFile = File(...),
) -> TagSuggestion | list[TagSuggestion]:
    """Upload photo to storage and return Claude's suggested tags.

    Two-step flow: this returns suggestions; frontend reviews/edits, then calls
    POST /clothes to commit.
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415, detail=f"Unsupported type {file.content_type}"
        )
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    # Normalize once: transcodes HEIC -> JPEG and shrinks oversized images.
    # Storage and Claude both get the same browser-safe bytes.
    image_bytes, mime_type = ensure_under_limit(image_bytes, file.content_type)

    _, public_url = upload_photo(image_bytes, file.filename or "photo", mime_type)

    try:
        tags = tag_clothing_photo(image_bytes, mime_type)
    except Exception as e:
        log.error("Tagging failed:\n%s", traceback.format_exc())
        delete_photo(public_url)
        raise HTTPException(status_code=502, detail="Tagging failed")

    if not tags:
        delete_photo(public_url)
        return []

    return TagSuggestion(photo_url=public_url, **tags)


@router.post("/upload-multi", response_model=list[TagSuggestion])
async def upload_and_tag_multi(file: UploadFile = File(...)) -> list[TagSuggestion]:
    """Upload one photo of multiple items; return one tag suggestion per item.

    B-full multi-item flow (#24 → #100): each item gets its own thumbnail,
    cropped from the model's bbox with padding; a missing/bad box falls back
    to the full photo for that item only (B-lite behavior — never fail the
    upload over a bad box). The shared original is uploaded for fallbacks and
    deleted again when every item got its own crop, so nothing orphans; when
    fallbacks do share it, the delete-time ref-count on photo_url still
    applies. Tagging runs before any upload, so a tagging failure or an empty
    result stores nothing.

    Cropping uses the same pre-fitted bytes the model saw (#96): past the
    vision API's silent-downscale limits, model bbox coordinates stop matching
    our pixels.
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415, detail=f"Unsupported type {file.content_type}"
        )
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    image_bytes, mime_type = ensure_under_limit(image_bytes, file.content_type)
    image_bytes, mime_type = fit_to_vision_limits(image_bytes, mime_type)

    try:
        tag_list = tag_clothing_photo_multi(image_bytes, mime_type)
    except Exception:
        log.error("Multi-tagging failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail="Tagging failed")

    if not tag_list:
        return []

    storage_path, original_url = upload_photo(
        image_bytes, file.filename or "photo", mime_type
    )
    stem = storage_path.rsplit(".", 1)[0]

    suggestions = []
    for i, tags in enumerate(tag_list):
        bbox = tags.pop("bbox", None)
        url = original_url
        try:
            crop_bytes = crop_to_bbox(image_bytes, bbox)
            if crop_bytes is None:
                log.warning(
                    "item %d: unusable bbox %r; falling back to full photo", i, bbox
                )
            else:
                _, url = upload_photo(
                    crop_bytes, "", "image/jpeg", storage_path=f"{stem}_item{i}.jpg"
                )
        except Exception:
            log.warning(
                "item %d: crop failed; falling back to full photo:\n%s",
                i,
                traceback.format_exc(),
            )
        suggestions.append(TagSuggestion(photo_url=url, **tags))

    if all(s.photo_url != original_url for s in suggestions):
        delete_photo(original_url)

    return suggestions


@router.post("", response_model=ClothingItem)
def create_item(item: ClothingItemCreate) -> ClothingItem:
    res = supabase().table("clothing_items").insert(item.model_dump()).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Insert returned no row")
    return ClothingItem(**res.data[0])


@router.get("", response_model=list[ClothingItem])
def list_items(available: bool | None = None, in_travel_bag: bool | None = None):
    q = supabase().table("clothing_items").select("*").order("created_at", desc=True)
    if available is not None:
        q = q.eq("available", available)
    if in_travel_bag is not None:
        q = q.eq("in_travel_bag", in_travel_bag)
    res = q.execute()
    return [ClothingItem(**row) for row in (res.data or [])]


@router.patch("/{item_id}", response_model=ClothingItem)
def update_item(item_id: str, patch: ClothingItemUpdate) -> ClothingItem:
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = supabase().table("clothing_items").update(fields).eq("id", item_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Item not found")
    return ClothingItem(**res.data[0])


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str) -> None:
    row = (
        supabase()
        .table("clothing_items")
        .select("photo_url")
        .eq("id", item_id)
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Item not found")
    photo_url = row.data[0]["photo_url"]
    supabase().table("clothing_items").delete().eq("id", item_id).execute()
    # Multi-item uploads (#24) share one storage object across N rows; only
    # delete the photo when this was the last row referencing it.
    remaining = (
        supabase()
        .table("clothing_items")
        .select("id", count="exact")
        .eq("photo_url", photo_url)
        .execute()
    )
    if not remaining.count:
        delete_photo(photo_url)
