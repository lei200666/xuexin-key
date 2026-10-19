from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime
import secrets
import os
from tablestore import OTSClient

# OTS 配置（从环境变量读取）
OTS_ENDPOINT = os.environ.get('OTS_ENDPOINT', '')
OTS_ACCESS_KEY_ID = os.environ.get('OTS_ACCESS_KEY_ID', '')
OTS_ACCESS_KEY_SECRET = os.environ.get('OTS_ACCESS_KEY_SECRET', '')
OTS_INSTANCE = os.environ.get('OTS_INSTANCE', '')

ADMIN_PASSWORD = 'Admin@2026'
ADMIN_TOKEN = 'xuexin_admin_token_2026'

# 初始化 OTS 客户端
ots_client = None
if OTS_ENDPOINT and OTS_ACCESS_KEY_ID and OTS_ACCESS_KEY_SECRET:
    ots_client = OTSClient(
        OTS_ENDPOINT,
        OTS_ACCESS_KEY_ID,
        OTS_ACCESS_KEY_SECRET,
        OTS_INSTANCE
    )

# 内存缓存
valid_keys = {}

class Handler(BaseHTTPRequestHandler):
    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def load_keys_from_ots(self):
        """从 OTS 加载卡密到内存"""
        if not ots_client:
            return
        try:
            # 查询 keys 表
            response = ots_client.get_range(
                table_name='keys',
                direction='FORWARD',
                inclusive_start_primary_key=[('key', '')],
                exclusive_end_primary_key=[('key', chr(0x10FFFF))],
                limit=1000
            )
            valid_keys.clear()
            for row in response.rows:
                key = row[0][1]
                key_data = {}
                for col in row[1]:
                    key_data[col[0]] = col[1]
                key_data['key'] = key
                valid_keys[key] = key_data
        except Exception as e:
            print(f'从 OTS 加载卡密失败: {e}')

    def do_GET(self):
        self.send_response(200)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if self.path.startswith('/admin/keys/') and self.path.endswith('/usage'):
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                parts = self.path.split('/')
                key = parts[3]
                usages = []
                if ots_client:
                    try:
                        response = ots_client.get_range(
                            table_name='key_usage',
                            direction='FORWARD',
                            inclusive_start_primary_key=[('key', key), ('ts', 0)],
                            exclusive_end_primary_key=[('key', key), ('ts', 9999999999999)],
                            limit=200
                        )
                        for row in response.rows:
                            ts = row[0][1]
                            device_id = ''
                            for col in row[1]:
                                if col[0] == 'device_id':
                                    device_id = col[1]
                            usages.append({'ts': ts, 'device_id': device_id})
                        usages.sort(key=lambda x: x['ts'], reverse=True)
                    except Exception as e:
                        print(f'查询使用记录失败: {e}')
                result = {'ok': True, 'usages': usages}
        elif self.path == '/admin/keys':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                # 从 OTS 加载最新数据
                self.load_keys_from_ots()
                keys = list(valid_keys.values())
                # 按 sort_order 排序，相同则按 created_at 排序
                keys.sort(key=lambda k: (k.get('sort_order', 0), k.get('created_at', 0)))
                result = {'ok': True, 'keys': keys}
        elif self.path == '/admin/profile':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                result = {'ok': True, 'profile': {
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
                }}
        else:
            result = {'ok': False, 'error': 'not found'}

        self.wfile.write(json.dumps(result).encode())

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()
        
        try:
            data = json.loads(body)
        except:
            data = {}

        self.send_response(200)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if self.path == '/admin/keys/import':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                keys = data.get('keys', [])
                count = 0
                if ots_client:
                    for k in keys:
                        key = str(k.get('key', '')).strip()
                        if not key:
                            continue
                        try:
                            attrs = [
                                ('duration_hours', k.get('duration_hours', -1)),
                                ('device_id', k.get('device_id', '')),
                                ('activated_at', k.get('activated_at', 0)),
                                ('is_revoked', k.get('is_revoked', False)),
                                ('created_at', k.get('created_at', 0)),
                                ('last_used_at', k.get('last_used_at', 0)),
                                ('note', k.get('note', '')),
                                ('sort_order', k.get('sort_order', 0))
                            ]
                            ots_client.put_row(
                                table_name='keys',
                                primary_key=[('key', key)],
                                attribute_columns=attrs
                            )
                            count += 1
                        except Exception as e:
                            print(f'导入卡密失败 {key}: {e}')
                result = {'ok': True, 'count': count}
        elif self.path == '/admin/keys/reorder':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                keys = data.get('keys', [])
                if ots_client:
                    for i, key in enumerate(keys):
                        try:
                            ots_client.update_row(
                                table_name='keys',
                                primary_key=[('key', key)],
                                update_of_attribute_columns=[('sort_order', i)]
                            )
                        except Exception as e:
                            print(f'更新排序失败: {e}')
                result = {'ok': True}
        elif self.path == '/verify' or self.path == '/':
            key = data.get('p_key', '').strip().upper()
            device_id = data.get('p_device_id', '')
            
            if not key:
                result = {'ok': False, 'error': '请输入卡密'}
            else:
                # 从 OTS 加载最新数据
                self.load_keys_from_ots()
                
                if key not in valid_keys:
                    result = {'ok': False, 'error': '卡密不存在'}
                else:
                    key_data = valid_keys[key]
                    
                    if key_data.get('is_revoked'):
                        result = {'ok': False, 'error': '该卡密已被停用'}
                    elif key_data.get('device_id') and key_data.get('device_id') != device_id:
                        result = {'ok': False, 'error': '卡密已绑定其他设备'}
                    else:
                        now_ts = int(datetime.now().timestamp())
                        if not key_data.get('device_id') and device_id:
                            key_data['device_id'] = device_id
                            key_data['activated_at'] = now_ts
                        key_data['last_used_at'] = now_ts
                        
                        # 写入 OTS
                        if ots_client:
                            try:
                                # ① 如果是首次激活，更新 device_id 和 activated_at
                                if not key_data.get('device_id') and device_id:
                                    ots_client.update_row(
                                        table_name='keys',
                                        primary_key=[('key', key)],
                                        update_of_attribute_columns=[
                                            ('device_id', device_id),
                                            ('activated_at', now_ts),
                                            ('last_used_at', now_ts)
                                        ]
                                    )
                                else:
                                    # ② 只更新 last_used_at
                                    ots_client.update_row(
                                        table_name='keys',
                                        primary_key=[('key', key)],
                                        update_of_attribute_columns=[('last_used_at', now_ts)]
                                    )
                                
                                # ③ 写一条使用记录
                                ots_client.put_row(
                                    table_name='key_usage',
                                    primary_key=[('key', key), ('ts', now_ts)],
                                    attribute_columns=[('device_id', device_id)]
                                )
                            except Exception as e:
                                print(f'记录使用失败: {e}')
                        
                        result = {
                            'ok': True,
                            'profile': {
                                'name': key_data.get('name', '测试用户'),
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
                        }
        elif self.path == '/admin/login':
            password = data.get('password', '')
            if password == ADMIN_PASSWORD:
                result = {'ok': True, 'token': ADMIN_TOKEN}
            else:
                result = {'ok': False, 'error': '密码错误'}
        elif self.path == '/admin/keys':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                duration_hours = data.get('duration_hours', -1)
                custom_key = data.get('key', '').strip().upper()
                
                # 自定义卡密格式校验
                if custom_key:
                    if not __import__('re').match(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', custom_key):
                        result = {'ok': False, 'error': '卡密格式错误，应为 XXXX-XXXX-XXXX（4-4-4，字母或数字）'}
                        self.wfile.write(json.dumps(result).encode())
                        return
                    new_key = custom_key
                else:
                    # 自动生成
                    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
                    key_parts = []
                    for i in range(3):
                        part = ''.join(secrets.choice(chars) for _ in range(4))
                        key_parts.append(part)
                    new_key = '-'.join(key_parts)
                
                # 检查卡密是否已存在
                if new_key in valid_keys:
                    result = {'ok': False, 'error': '卡密已存在，请换一个'}
                else:
                    # 保存到 OTS
                    if ots_client:
                        try:
                            ots_client.put_row(
                                table_name='keys',
                                primary_key=[('key', new_key)],
                                attribute_columns=[
                                    ('duration_hours', duration_hours),
                                    ('device_id', ''),
                                    ('activated_at', 0),
                                    ('is_revoked', False),
                                    ('created_at', int(datetime.now().timestamp() * 1000)),
                                    ('sort_order', 0),
                                    ('note', '')
                                ]
                            )
                        except Exception as e:
                            print(f'保存到 OTS 失败: {e}')
                    
                    valid_keys[new_key] = {
                        'key': new_key,
                        'name': '',
                        'device_id': '',
                        'duration_hours': duration_hours,
                        'activated_at': 0,
                        'is_revoked': False,
                        'created_at': int(datetime.now().timestamp() * 1000),
                        'note': ''
                    }
                    result = {'ok': True, 'key': new_key}
        else:
            result = {'ok': False, 'error': 'not found'}

        self.wfile.write(json.dumps(result).encode())

    def do_PATCH(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()
        
        try:
            data = json.loads(body)
        except:
            data = {}

        self.send_response(200)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if self.path.startswith('/admin/keys/'):
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                key = self.path.split('/')[-1]
                if key in valid_keys:
                    if 'is_revoked' in data:
                        valid_keys[key]['is_revoked'] = data['is_revoked']
                        # 同步到 OTS
                        if ots_client:
                            try:
                                ots_client.update_row(
                                    table_name='keys',
                                    primary_key=[('key', key)],
                                    update_of_attribute_columns=[('is_revoked', data['is_revoked'])]
                                )
                            except Exception as e:
                                print(f'更新 OTS 失败: {e}')
                    if 'duration_hours' in data:
                        valid_keys[key]['duration_hours'] = data['duration_hours']
                    if 'note' in data:
                        valid_keys[key]['note'] = data['note']
                    result = {'ok': True}
                else:
                    result = {'ok': False, 'error': '卡密不存在'}
        elif self.path == '/admin/profile':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                result = {'ok': True}
        else:
            result = {'ok': False, 'error': 'not found'}

        self.wfile.write(json.dumps(result).encode())

    def do_DELETE(self):
        self.send_response(200)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if self.path.startswith('/admin/keys/'):
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                key = self.path.split('/')[-1]
                if key in valid_keys:
                    del valid_keys[key]
                    # 从 OTS 删除
                    if ots_client:
                        try:
                            ots_client.delete_row(
                                table_name='keys',
                                primary_key=[('key', key)]
                            )
                        except Exception as e:
                            print(f'从 OTS 删除失败: {e}')
                    result = {'ok': True}
                else:
                    result = {'ok': False, 'error': '卡密不存在'}
        else:
            result = {'ok': False, 'error': 'not found'}

        self.wfile.write(json.dumps(result).encode())

if __name__ == '__main__':
    # 从 OTS 加载卡密
    if ots_client:
        try:
            response = ots_client.get_range(
                table_name='keys',
                direction='FORWARD',
                inclusive_start_primary_key=[('key', '')],
                exclusive_end_primary_key=[('key', chr(0x10FFFF))],
                limit=1000
            )
            for row in response.rows:
                key = row[0][1]
                key_data = {}
                for col in row[1]:
                    key_data[col[0]] = col[1]
                key_data['key'] = key
                valid_keys[key] = key_data
            print(f'从 OTS 加载了 {len(valid_keys)} 张卡密')
        except Exception as e:
            print(f'从 OTS 加载卡密失败: {e}')
    else:
        print('OTS 客户端未初始化，环境变量未配置')
    
    server = HTTPServer(('0.0.0.0', 9000), Handler)
    print('Server running on port 9000')
    server.serve_forever()
