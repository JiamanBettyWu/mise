-- Issue #81: default retail department for purchase search.
--
-- This is deliberately named shopping_department, not gender: the value controls
-- Google Shopping query targeting, not identity.
--
-- Run in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

alter table profile
  add column if not exists shopping_department text not null default 'womens';

do $$
begin
  alter table profile
    add constraint profile_shopping_department_check
    check (shopping_department in ('womens', 'mens', 'unisex', 'no_preference'));
exception
  when duplicate_object then null;
end $$;
