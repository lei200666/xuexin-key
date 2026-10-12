-- =====================================================================
-- 学信卡密项目 · 安全改造 SQL
-- 在 Supabase Dashboard → SQL Editor 中执行
-- =====================================================================

-- ============ 第一部分：开启 RLS + 收紧权限 ============

alter table public.keys enable row level security;

revoke all on table public.keys from anon;

revoke all on table public.keys from authenticated;
grant select, insert, update, delete on table public.keys to authenticated;

-- ============ 第二部分：卡密校验 RPC ============

create or replace function public.verify_key(
  p_key text,
  p_device_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  k record;
begin
  p_key := upper(trim(p_key));

  select * into k
  from public.keys
  where key = p_key
  for update;

  if not found then
    return jsonb_build_object('ok', false, 'error', '卡密不存在');
  end if;

  if k.is_revoked then
    return jsonb_build_object('ok', false, 'error', '该卡密已被停用');
  end if;

  if k.device_id is not null and k.device_id <> p_device_id then
    return jsonb_build_object('ok', false, 'error', '该卡密已绑定其他设备');
  end if;

  if k.duration_hours <> -1 and k.activated_at is not null then
    if now() > k.activated_at + make_interval(hours => k.duration_hours::int) then
      return jsonb_build_object('ok', false, 'error', '卡密已过期');
    end if;
  end if;

  if k.device_id is null then
    update public.keys
    set device_id = p_device_id,
        activated_at = now()
    where key = p_key;
  end if;

  return jsonb_build_object('ok', true);
end;
$$;

revoke all on function public.verify_key(text, text) from public;
grant execute on function public.verify_key(text, text) to anon;
grant execute on function public.verify_key(text, text) to authenticated;

-- ============ 第三部分：管理员权限策略（拿到管理员 UUID 后执行） ============
-- 注意：如果之前已创建过名为 admin_manage_keys 的策略，需先执行：
--   drop policy if exists "admin_manage_keys" on public.keys;
-- 再把两处 '这里替换成管理员UUID' 换成真实 UUID。

drop policy if exists "admin_manage_keys" on public.keys;

create policy "admin_manage_keys"
on public.keys
for all
to authenticated
using (auth.uid() = '这里替换成管理员UUID')
with check (auth.uid() = '这里替换成管理员UUID');
