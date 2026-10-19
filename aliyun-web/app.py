from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime
import secrets
import os
import re
from tablestore import OTSClient, Row, Condition, RowExistenceExpectation

# OTS 配置（从环境变量读取）
OTS_ENDPOINT = os.environ.get('OTS_ENDPOINT', '')
OTS_ACCESS_KEY_ID = os.environ.get('OTS_ACCESS_KEY_ID', '')
OTS_ACCESS_KEY_SECRET = os.environ.get('OTS_ACCESS_KEY_SECRET', '')
OTS_INSTANCE = os.environ.get('OTS_INSTANCE', '')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '')

KEYS_TABLE = 'keys'
USAGE_TABLE = 'key_usage'

# 初始化 OTS 客户端
ots_client = None
if OTS_ENDPOINT and OTS_ACCESS_KEY_ID and OTS_ACCESS_KEY_SECRET:
    ots_client = OTSClient(
        OTS_ENDPOINT,
        OTS_ACCESS_KEY_ID,
        OTS_ACCESS_KEY_SECRET,
        OTS_INSTANCE
    )


# ========== OTS 工具函数 ==========

def get_all_keys():
    """从 OTS 查询所有卡密，自动分页，返回列表"""
    if not ots_client:
        return []
    
    all_rows = []
    next_start = None
    
    while True:
        kwargs = {
            'table_name': KEYS_TABLE,
            'direction': 'FORWARD',
            'inclusive_start_primary_key': next_start if next_start else [('key', '')],
            'exclusive_end_primary_key': [('key', chr(0x10FFFF))],
            'limit': 100
        }
        response = ots_client.get_range(**kwargs)
        rows = response[2]
        next_start = response[1]  # next_start_primary_key
        
        all_rows.extend(rows)
        
        if not next_start:
            break
    
    # 转换成字典列表
    keys = []
    for row in all_rows:
        key = row.primary_key[0][1]
        key_data = {}
        for col in row.attribute_columns:
            key_data[col[0]] = col[1]
        key_data['key'] = key
        keys.append(key_data)
    
    # 排序
    keys.sort(key=lambda k: (k.get('sort_order', 0), k.get('created_at', 0)))
    return keys


def get_one_key(key):
    """从 OTS 查询单张卡密，返回字典或 None"""
    try:
        response = ots_client.get_row(
            table_name=KEYS_TABLE,
            primary_key=[('key', key)]
        )
        row = response[1]  # consumed, return_row, ...
        if not row:
            return None
        key_data = {}
        for col in row.attribute_columns:
            key_data[col[0]] = col[1]
        key_data['key'] = key
        return key_data
    except Exception:
        return None


def put_key(key_data):
    """写入/覆盖一张卡密到 OTS"""
    row = Row(
        primary_key=[('key', key_data['key'])],
        attribute_columns=[
            ('duration_hours', key_data.get('duration_hours', -1)),
            ('device_id', key_data.get('device_id', '')),
            ('activated_at', key_data.get('activated_at', 0)),
            ('is_revoked', key_data.get('is_revoked', False)),
            ('created_at', key_data.get('created_at', 0)),
            ('last_used_at', key_data.get('last_used_at', 0)),
            ('note', key_data.get('note', '')),
            ('sort_order', key_data.get('sort_order', 0))
        ]
    )
    ots_client.put_row(table_name=KEYS_TABLE, row=row)


def delete_key(key):
    """从 OTS 删除一张卡密"""
    row_delete = Row(primary_key=[('key', key)], attribute_columns=[])
    condition = Condition(RowExistenceExpectation.EXPECT_EXIST, None)
    ots_client.delete_row(table_name=KEYS_TABLE, row=row_delete, condition=condition)


def get_usage_records(key, limit=200):
    """查询某张卡密的使用记录"""
    response = ots_client.get_range(
        table_name=USAGE_TABLE,
        direction='FORWARD',
        inclusive_start_primary_key=[('key', key), ('ts', 0)],
        exclusive_end_primary_key=[('key', key), ('ts', 9999999999999)],
        limit=limit
    )
    rows = response[2]
    records = []
    for row in rows:
        ts = row.primary_key[1][1]
        device_id = ''
        for col in row.attribute_columns:
            if col[0] == 'device_id':
                device_id = col[1]
        records.append({'ts': ts, 'device_id': device_id})
    records.sort(key=lambda x: x['ts'], reverse=True)
    return records


def add_usage_record(key, ts, device_id):
    """添加一条使用记录"""
    row = Row(
        primary_key=[('key', key), ('ts', ts)],
        attribute_columns=[('device_id', device_id)]
    )
    ots_client.put_row(table_name=USAGE_TABLE, row=row)


# ========== HTTP 处理器 ==========

class Handler(BaseHTTPRequestHandler):
    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def send_json(self, result, status=200):
        self.send_response(status)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def check_auth(self):
        auth = self.headers.get('Authorization', '')
        return auth == 'Bearer ' + ADMIN_TOKEN

    def read_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()
        try:
            return json.loads(body)
        except Exception:
            return {}

    # ========== GET ==========

    def do_GET(self):
        if self.path.startswith('/admin/keys/') and self.path.endswith('/usage'):
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            parts = self.path.split('/')
            key = parts[3]
            try:
                records = get_usage_records(key) if ots_client else []
                self.send_json({'ok': True, 'usages': records})
            except Exception as e:
                self.send_json({'ok': False, 'error': f'查询使用记录失败: {str(e)}'})

        elif self.path == '/admin/keys':
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            try:
                keys = get_all_keys() if ots_client else []
                self.send_json({'ok': True, 'keys': keys})
            except Exception as e:
                self.send_json({'ok': False, 'error': f'查询卡密列表失败: {str(e)}'})

        elif self.path == '/admin/profile':
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            self.send_json({'ok': True, 'profile': get_profile_data()})

        else:
            self.send_json({'ok': False, 'error': 'not found'}, 404)

    # ========== POST ==========

    def do_POST(self):
        data = self.read_body()

        if self.path == '/admin/login':
            password = data.get('password', '')
            if password == ADMIN_PASSWORD:
                self.send_json({'ok': True, 'token': ADMIN_TOKEN})
            else:
                self.send_json({'ok': False, 'error': '密码错误'})

        elif self.path == '/verify' or self.path == '/':
            self.handle_verify(data)

        elif self.path == '/admin/keys':
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            self.handle_gen_key(data)

        elif self.path == '/admin/keys/import':
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            self.handle_import(data)

        elif self.path == '/admin/keys/reorder':
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            self.handle_reorder(data)

        else:
            self.send_json({'ok': False, 'error': 'not found'}, 404)

    # ========== PATCH ==========

    def do_PATCH(self):
        data = self.read_body()

        if self.path.startswith('/admin/keys/'):
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            key = self.path.split('/')[-1]
            try:
                key_data = get_one_key(key)
                if not key_data:
                    self.send_json({'ok': False, 'error': '卡密不存在'})
                    return

                # 更新字段
                if 'is_revoked' in data:
                    key_data['is_revoked'] = data['is_revoked']
                if 'duration_hours' in data:
                    key_data['duration_hours'] = data['duration_hours']
                if 'note' in data:
                    key_data['note'] = data['note']

                # 写回 OTS
                put_key(key_data)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': f'更新失败: {str(e)}'})

        elif self.path == '/admin/profile':
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            self.send_json({'ok': True})

        else:
            self.send_json({'ok': False, 'error': 'not found'}, 404)

    # ========== DELETE ==========

    def do_DELETE(self):
        if self.path.startswith('/admin/keys/'):
            if not self.check_auth():
                self.send_json({'ok': False, 'error': '未授权'})
                return
            key = self.path.split('/')[-1]
            try:
                key_data = get_one_key(key)
                if not key_data:
                    self.send_json({'ok': False, 'error': '卡密不存在'})
                    return
                delete_key(key)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': f'删除失败: {str(e)}'})
        else:
            self.send_json({'ok': False, 'error': 'not found'}, 404)

    # ========== 业务逻辑 ==========

    def handle_verify(self, data):
        """卡密验证"""
        key = data.get('p_key', '').strip().upper()
        device_id = data.get('p_device_id', '')

        if not key:
            self.send_json({'ok': False, 'error': '请输入卡密'})
            return

        try:
            key_data = get_one_key(key)
            if not key_data:
                self.send_json({'ok': False, 'error': '卡密不存在'})
                return

            if key_data.get('is_revoked'):
                self.send_json({'ok': False, 'error': '该卡密已被停用'})
                return

            if key_data.get('device_id') and key_data.get('device_id') != device_id:
                self.send_json({'ok': False, 'error': '卡密已绑定其他设备'})
                return

            now_ts = int(datetime.now().timestamp())

            # 首次激活
            if not key_data.get('device_id') and device_id:
                key_data['device_id'] = device_id
                key_data['activated_at'] = now_ts

            key_data['last_used_at'] = now_ts

            # 写回 keys 表
            put_key(key_data)

            # 写使用记录
            add_usage_record(key, now_ts, device_id)

            self.send_json({
                'ok': True,
                'profile': get_profile_data()
            })

        except Exception as e:
            self.send_json({'ok': False, 'error': f'验证失败: {str(e)}'})

    def handle_gen_key(self, data):
        """生成卡密"""
        duration_hours = data.get('duration_hours', -1)
        custom_key = data.get('key', '').strip().upper()

        try:
            if custom_key:
                # 自定义格式校验
                if not re.match(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', custom_key):
                    self.send_json({'ok': False, 'error': '卡密格式错误，应为 XXXX-XXXX-XXXX（4-4-4，字母或数字）'})
                    return
                new_key = custom_key
            else:
                # 自动生成
                chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
                for _ in range(10):
                    key_parts = [
                        ''.join(secrets.choice(chars) for _ in range(4))
                        for _ in range(3)
                    ]
                    new_key = '-'.join(key_parts)
                    if not get_one_key(new_key):
                        break
                else:
                    self.send_json({'ok': False, 'error': '生成卡密失败，请重试'})
                    return

            # 检查是否已存在
            if get_one_key(new_key):
                self.send_json({'ok': False, 'error': '卡密已存在，请换一个'})
                return

            now_ts = int(datetime.now().timestamp())

            key_data = {
                'key': new_key,
                'duration_hours': duration_hours,
                'device_id': '',
                'activated_at': 0,
                'is_revoked': False,
                'created_at': now_ts,
                'last_used_at': 0,
                'note': '',
                'sort_order': 0
            }

            # 写入（不存在才写）
            row = Row(
                primary_key=[('key', new_key)],
                attribute_columns=[
                    ('duration_hours', duration_hours),
                    ('device_id', ''),
                    ('activated_at', 0),
                    ('is_revoked', False),
                    ('created_at', now_ts),
                    ('last_used_at', 0),
                    ('note', ''),
                    ('sort_order', 0)
                ]
            )
            condition = Condition(RowExistenceExpectation.EXPECT_NOT_EXIST, None)
            ots_client.put_row(table_name=KEYS_TABLE, row=row, condition=condition)

            self.send_json({'ok': True, 'key': new_key})

        except Exception as e:
            self.send_json({'ok': False, 'error': f'保存卡密失败: {str(e)}'})

    def handle_import(self, data):
        """导入卡密"""
        keys = data.get('keys', [])
        count = 0
        try:
            for k in keys:
                key = str(k.get('key', '')).strip()
                if not key:
                    continue
                key_data = {
                    'key': key,
                    'duration_hours': k.get('duration_hours', -1),
                    'device_id': k.get('device_id', ''),
                    'activated_at': k.get('activated_at', 0),
                    'is_revoked': k.get('is_revoked', False),
                    'created_at': k.get('created_at', 0),
                    'last_used_at': k.get('last_used_at', 0),
                    'note': k.get('note', ''),
                    'sort_order': k.get('sort_order', 0)
                }
                put_key(key_data)
                count += 1
            self.send_json({'ok': True, 'count': count})
        except Exception as e:
            self.send_json({'ok': False, 'error': f'导入卡密失败: {str(e)}'})

    def handle_reorder(self, data):
        """排序"""
        keys = data.get('keys', [])
        try:
            for i, key in enumerate(keys):
                key_data = get_one_key(key)
                if key_data:
                    key_data['sort_order'] = i
                    put_key(key_data)
            self.send_json({'ok': True})
        except Exception as e:
            self.send_json({'ok': False, 'error': f'更新排序失败: {str(e)}'})


# ========== 学生档案数据 ==========

def get_profile_data():
    return {
        'name': '测试用户',
        'school': '安阳学院',
        'major': '机电一体化技术',
        'gender': '男',
        'birth_date': '2006年08月01日',
        'nation': '汉族',
        'id_number': '41112320060801XXXX',
        'study_period': '3年',
        'education_type': '普通高等教育',
        'campus': '安阳校区',
        'department': '航空工程学院',
        'class_name': '2401',
        'student_id': '242700XXX',
        'enrollment_date': '2024年09月01日',
        'status': '在籍（注册学籍）',
        'graduation_date': '2027年07月01日'
    }


# ========== 启动 ==========

if __name__ == '__main__':
    if not ots_client:
        print('警告：OTS 客户端未初始化，请检查 OTS 环境变量')
    else:
        print('OTS 客户端初始化成功')

    server = ThreadingHTTPServer(('0.0.0.0', 9000), Handler)
    print('Server running on port 9000')
    server.serve_forever()
