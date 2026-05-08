# Migrations

Run these in Supabase → SQL Editor in order. Each is idempotent.

## 001 — add description + brand (Phase 2.1)

```sql
alter table public.clothing_items
  add column if not exists description text not null default '',
  add column if not exists brand text;
```
