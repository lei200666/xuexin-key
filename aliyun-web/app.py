from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime
import secrets

# 卡密列表（写死在代码里）
valid_keys = {
    'FF7E-KEZ2-2GYX': {
        'key': 'FF7E-KEZ2-2GYX',
        'name': '测试用户',
        'device_id': '',
        'duration_hours': -1,
        'activated_at': 0,
        'is_revoked': False,
        'created_at': 1728000000000,
        'note': ''
    },
    'ZM4Q-4A5Q-LN2L': {
        'key': 'ZM4Q-4A5Q-LN2L',
        'name': '纯牛马',
        'device_id': '',
        'duration_hours': -1,
        'activated_at': 0,
        'is_revoked': False,
        'created_at': 1728000000000,
        'note': ''
    }
}

ADMIN_PASSWORD = 'Admin@2026'
ADMIN_TOKEN = 'xuexin_admin_token_2026'

class Handler(BaseHTTPRequestHandler):
    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        if self.path == '/admin/keys':
            # 检查 token
            auth = self.headers.get('Authorization', '')
            if auth != 'Bearer ' + ADMIN_TOKEN:
                result = {'ok': False, 'error': '未授权'}
            else:
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
            elif key not in valid_keys:
                result = {'ok': False, 'error': '卡密不存在'}
            else:
                key_data = valid_keys[key]
                
                if key_data['is_revoked']:
                    result = {'ok': False, 'error': '该卡密已被停用'}
                elif key_data['device_id'] and key_data['device_id'] != device_id:
                    result = {'ok': False, 'error': '卡密已绑定其他设备'}
                else:
                    if not key_data['device_id'] and device_id:
                        key_data['device_id'] = device_id
                        key_data['activated_at'] = int(datetime.now().timestamp())
                    
                    result = {
                        'ok': True,
                        'profile': {
                            'name': key_data['name'],
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
                # 生成随机卡密
                chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
                key_parts = []
                for i in range(3):
                    part = ''.join(secrets.choice(chars) for _ in range(4))
                    key_parts.append(part)
                new_key = '-'.join(key_parts)
                
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
                    result = {'ok': True}
                else:
                    result = {'ok': False, 'error': '卡密不存在'}
        else:
            result = {'ok': False, 'error': 'not found'}

        self.wfile.write(json.dumps(result).encode())

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 9000), Handler)
    print('Server running on port 9000')
    server.serve_forever()
