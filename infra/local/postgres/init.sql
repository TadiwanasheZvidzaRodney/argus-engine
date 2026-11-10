-- Local-only bootstrap. Production roles are created by Terraform + migrations.
create extension if not exists pgcrypto;
create extension if not exists citext;

-- Application role used by services; RLS policies arrive in Phase 1.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'argus_app') then
    create role argus_app login password 'argus_app';
  end if;
end
$$;

grant connect on database argus to argus_app;
alter default privileges in schema public grant select, insert, update, delete on tables to argus_app;
grant usage on schema public to argus_app;
