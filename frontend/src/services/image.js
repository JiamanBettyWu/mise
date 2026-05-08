const MAX_DIM = 1600;
const QUALITY = 0.85;
const TARGET_BYTES = 4_500_000; // stay safely under Claude's 5MB limit

export async function compressImage(file) {
  if (!file.type.startsWith('image/') || file.size <= TARGET_BYTES) return file;

  try {
    const bitmap = await loadBitmap(file);
    const { width, height } = scaledSize(bitmap.width, bitmap.height, MAX_DIM);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.getContext('2d').drawImage(bitmap, 0, 0, width, height);

    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', QUALITY)
    );
    if (!blob) return file;

    const newName = file.name.replace(/\.[^.]+$/, '') + '.jpg';
    return new File([blob], newName, { type: 'image/jpeg' });
  } catch {
    return file; // fall back to original (e.g. HEIC the browser can't decode)
  }
}

async function loadBitmap(file) {
  if ('createImageBitmap' in window) {
    try { return await createImageBitmap(file); } catch { /* fall through */ }
  }
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

function scaledSize(w, h, max) {
  if (w <= max && h <= max) return { width: w, height: h };
  const ratio = Math.min(max / w, max / h);
  return { width: Math.round(w * ratio), height: Math.round(h * ratio) };
}
