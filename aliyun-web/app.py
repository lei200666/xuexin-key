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

        if self.path == '/admin/keys':
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
                # 从 OTS 加载最新数据
                self.load_keys_from_ots()
                keys = list(valid_keys.values())
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

        if self.path == '/verify' or self.path == '/':
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
                        if not key_data.get('device_id') and device_id:
                            key_data['device_id'] = device_id
                            key_data['activated_at'] = int(datetime.now().timestamp())
                        
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
                chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
                key_parts = []
                for i in range(3):
                    part = ''.join(secrets.choice(chars) for _ in range(4))
                    key_parts.append(part)
                new_key = '-'.join(key_parts)
                
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
    # 初始化内存缓存（先放几个测试卡密）
    valid_keys['FF7E-KEZ2-2GYX'] = {
        'key': 'FF7E-KEZ2-2GYX',
        'name': '测试用户',
        'device_id': '',
        'duration_hours': -1,
        'activated_at': 0,
        'is_revoked': False,
        'created_at': 1728000000000,
        'note': ''
    }
    valid_keys['ZM4Q-4A5Q-LN2L'] = {
        'key': 'ZM4Q-4A5Q-LN2L',
        'name': '纯牛马',
        'device_id': '',
        'duration_hours': -1,
        'activated_at': 0,
        'is_revoked': False,
        'created_at': 1728000000000,
        'note': ''
    }
    
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
    
    server = HTTPServer(('0.0.0.0', 9000), Handler)
    print('Server running on port 9000')
    server.serve_forever()
