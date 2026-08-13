-- Grants for PostgREST roles (local + hosted). Tables are pipeline-owned; service_role writes.

begin;

grant usage on schema public to anon, authenticated, service_role;

grant select on all tables in schema public to anon, authenticated, service_role;
grant insert, update, delete on all tables in schema public to service_role;

grant usage, select on all sequences in schema public to anon, authenticated, service_role;

grant execute on all functions in schema public to anon, authenticated, service_role;

alter default privileges in schema public
  grant select on tables to anon, authenticated, service_role;
alter default privileges in schema public
  grant insert, update, delete on tables to service_role;
alter default privileges in schema public
  grant usage, select on sequences to anon, authenticated, service_role;
alter default privileges in schema public
  grant execute on functions to anon, authenticated, service_role;

commit;
