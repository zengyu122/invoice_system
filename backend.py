#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import time
import datetime
import logging
import sqlite3
import hashlib
import jwt
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from io import BytesIO
import pdfplumber
import pandas as pd

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class User:
    """用户数据类"""
    id: int
    username: str
    email: str
    created_at: datetime.datetime
    last_login: datetime.datetime


@dataclass
class Invoice:
    """发票数据类"""
    id: int
    user_id: int
    filename: str
    person_name: str
    invoice_code: str
    invoice_number: str
    invoice_date: str
    amount: float
    tax_rate: str
    tax_amount: float
    total_amount: float
    status: str
    extracted_at: datetime.datetime
    created_at: datetime.datetime
    shenheyuefen: str
    shiyebu: str
    daxiangmu: str


@dataclass
class SystemConfig:
    """系统配置类"""
    id: int
    config_key: str
    config_value: str
    description: str


class DatabaseManager:
    """数据库管理类"""

    def __init__(self, db_path="invoice_system.db"):
        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def init_database(self):
        """初始化数据库表 - 修复版本"""
        conn = self.get_connection()
        try:
            # 用户表 - 修复表结构
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            ''')
            # 检查并添加缺失的列
            self._check_and_add_columns(conn)

            # 发票数据表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    shenheyuefen TEXT,
                    shiyebu TEXT,
                    daxiangmu TEXT,
                    filename TEXT NOT NULL,
                    person_name TEXT,
                    invoice_code TEXT,
                    invoice_number TEXT,
                    invoice_date TEXT,
                    amount REAL,
                    tax_rate TEXT,
                    tax_amount REAL,
                    total_amount REAL,
                    status TEXT,
                    extracted_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')

            # 系统配置表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_key TEXT UNIQUE NOT NULL,
                    config_value TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 菜单功能表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS menu_functions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    function_name TEXT UNIQUE NOT NULL,
                    icon TEXT,
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 操作日志表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    operation_type TEXT,
                    operation_detail TEXT,
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')

            # 插入默认数据
            self._insert_default_data(conn)
            conn.commit()
        except Exception as e:
            logger.error(f"数据库初始化错误: {e}")
            # 如果表结构有问题，重新创建数据库
            self._recreate_database()
        finally:
            conn.close()

    def _check_and_add_columns(self, conn):
        """检查并添加缺失的列"""
        # 检查users表结构
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        # 添加缺失的email列
        if 'email' not in columns:
            logger.info("添加email列到users表")
            conn.execute('ALTER TABLE users ADD COLUMN email TEXT')

        # 添加缺失的last_login列
        if 'last_login' not in columns:
            logger.info("添加last_login列到users表")
            conn.execute('ALTER TABLE users ADD COLUMN last_login TIMESTAMP')

        conn.commit()

    def _recreate_database(self):
        """重新创建数据库（解决表结构冲突）"""
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
                logger.info("删除旧数据库文件，重新创建")
            self.init_database()
        except Exception as e:
            logger.error(f"重新创建数据库失败: {e}")

    def _insert_default_data(self, conn):
        """插入默认数据 - 修复版本"""
        try:
            # 检查email列是否存在，如果不存在则添加
            cursor = conn.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'email' not in columns:
                logger.info("添加email列到users表")
                conn.execute('ALTER TABLE users ADD COLUMN email TEXT')

            # 默认管理员用户
            default_password = hashlib.sha256("admin123".encode()).hexdigest()
            # default_password = "admin123"
            conn.execute('''
                INSERT OR IGNORE INTO users (username, password_hash, email) 
                VALUES (?, ?, ?)
            ''', ('admin', default_password, 'admin@invoice.com'))

            # 系统配置
            configs = [
                ('system_name', '智能发票提取系统', '系统名称'),
                ('system_version', 'v2.0.0', '系统版本'),
                ('company_name', '发票科技有限公司', '公司名称'),
                ('max_upload_files', '1000', '最大上传文件数'),
                ('default_date_format', 'YYYY-MM-DD', '默认日期格式'),
                ('default_output_format', 'Excel', '默认输出格式')
            ]

            for key, value, desc in configs:
                conn.execute('''
                    INSERT OR IGNORE INTO system_config (config_key, config_value, description)
                    VALUES (?, ?, ?)
                ''', (key, value, desc))

            # 菜单功能
            menu_items = [
                ('发票提取', '📁', '批量提取发票信息', 1),
                ('结果查看', '📊', '查看处理结果', 2),
                ('数据分析', '📈', '数据可视化分析', 3),
                ('系统设置', '⚙️', '系统配置管理', 4),
                ('使用帮助', '❓', '使用说明文档', 5)
            ]

            for name, icon, desc, order in menu_items:
                conn.execute('''
                    INSERT OR IGNORE INTO menu_functions (function_name, icon, description, sort_order)
                    VALUES (?, ?, ?, ?)
                ''', (name, icon, desc, order))

        except Exception as e:
            logger.error(f"插入默认数据错误: {e}")
            raise


class AuthService:
    """认证服务类"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.secret_key = "invoice_system_secret_key_2024_v2"
        self.token_expire_hours = 24  # Token有效期24小时

    def generate_token(self, user_id: int, username: str) -> str:
        """生成JWT Token"""
        payload = {
            'user_id': user_id,
            'username': username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24),
            'iat': datetime.datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def verify_token(self, token: str) -> Optional[dict]:
        """验证JWT Token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None  # Token过期
        except jwt.InvalidTokenError:
            return None  # Token无效

    def verify_user(self, username: str, password: str) -> Optional[User]:
        """验证用户并返回Token"""
        conn = self.db_manager.get_connection()
        try:
            cursor = conn.execute(
                'SELECT id, username, password_hash, email FROM users WHERE username = ?',
                (username,)
            )
            result = cursor.fetchone()

            if result:
                user_id, username, password_hash, email = result
                # 简单的密码验证（实际应用中应该使用更安全的方式）
                if hashlib.sha256(password.encode()).hexdigest() == password_hash:
                    # 更新最后登录时间
                    conn.execute(
                        'UPDATE users SET last_login = ? WHERE id = ?',
                        (datetime.datetime.now(), user_id)
                    )
                    conn.commit()

                    return User(
                        id=user_id,
                        username=username,
                        email=email,
                        created_at=datetime.datetime.now(),
                        last_login=datetime.datetime.now()
                    )
            return None
        except Exception as e:
            logger.error(f"用户验证错误: {e}")
            return None
        finally:
            conn.close()


class InvoiceExtractor:
    """发票提取器类"""

    def __init__(self):
        self.date_patterns = self._init_date_patterns()
        self.amount_patterns = self._init_amount_patterns()
        self.name_patterns = self._init_name_patterns()

    def _init_date_patterns(self) -> List[Tuple[str, str]]:
        return [
            (r'开票日期\s*[:：]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', '标准格式(带空格)'),
            (r'开票日期\s*[:：]\s*(\d{4})年(\d{1,2})月(\d{1,2})日', '标准格式(无空格)'),
        ]

    def _init_amount_patterns(self) -> List[Tuple[str, str]]:
        return [
            (r'(\d+\.\d{2})\s+(\d+)%\s+(\d+\.\d{2})', '表格格式'),
            (r'[￥¥]\s*(\d+\.\d{2})', '人民币符号'),
        ]

    def _init_name_patterns(self) -> List[Tuple[str, str]]:
        return [
            (r'滴滴电子发票\d+[_-]\d+[_-]([\u4e00-\u9fa5]{2,4})\.pdf$', '滴滴发票格式'),
            (r'([\u4e00-\u9fa5]{2,4})\.pdf$', '直接匹配'),
        ]

    def extract_invoice_info(self, pdf_path: str) -> Dict:
        """提取发票信息"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = pdf.pages[0].extract_text()

            result = {}

            # 提取发票代码
            code_match = re.search(r'发票代码\s*[:：]\s*(\d+)', text)
            result['发票代码'] = code_match.group(1) if code_match else ""

            # 提取发票号码
            no_match = re.search(r'发票号码\s*[:：]\s*(\d+)', text)
            result['发票号码'] = no_match.group(1) if no_match else ""

            # 提取开票日期
            date_match = None
            for pattern, _ in self.date_patterns:
                date_match = re.search(pattern, text)
                if date_match:
                    year, month, day = date_match.groups()
                    result['开票日期'] = f"{year}/{month.zfill(2)}/{day.zfill(2)}"
                    break
            else:
                result['开票日期'] = ""

            # 提取金额和税额
            total_amount, tax_amount = self._extract_amounts(text)
            result['金额'] = total_amount if total_amount else 0.0
            result['税额'] = tax_amount if tax_amount else 0.0
            result['价税合计'] = result['金额'] + result['税额']

            # 计算税率
            if result['金额'] > 0:
                tax_rate = (result['税额'] / result['金额']) * 100
                result['税率'] = f"{tax_rate:.0f}%"
            else:
                result['税率'] = "0%"

            result['文件名'] = os.path.basename(pdf_path)
            result['提取时间'] = datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')
            result['状态'] = '成功'

            return result

        except Exception as e:
            return {
                '文件名': os.path.basename(pdf_path),
                '提取时间': datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
                '状态': f'失败: {str(e)}'
            }

    def _extract_amounts(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        # 表格格式匹配
        table_match = re.search(r'(\d+\.\d{2})\s+(\d+)%\s+(\d+\.\d{2})', text)
        if table_match:
            return float(table_match.group(1)), float(table_match.group(3))

        # 人民币符号匹配
        yuan_matches = re.findall(r'[￥¥]\s*(\d+\.\d{2})', text)
        if len(yuan_matches) >= 2:
            return float(yuan_matches[0]), float(yuan_matches[1])

        return None, None

    def extract_person_name(self, filename: str) -> str:
        """从文件名提取姓名"""
        for pattern, _ in self.name_patterns:
            match = re.search(pattern, filename)
            if match:
                name = match.group(1)
                if 2 <= len(name) <= 4:
                    return name

        # 备用方法
        name_without_ext = filename.replace('.pdf', '')
        chinese_names = re.findall(r'[\u4e00-\u9fa5]{2,4}', name_without_ext)
        if chinese_names:
            return max(chinese_names, key=len)
        return "未知"


class InvoiceService:
    """发票服务类"""

    def __init__(self, db_manager: DatabaseManager, extractor: InvoiceExtractor):
        self.db_manager = db_manager
        self.extractor = extractor

    def _save_to_database(self, result: Dict, user_id: int):
        """保存到数据库"""
        required_fields = [
            '文件名', '姓名', '发票代码', '发票号码', '开票日期',
            '金额', '税率', '税额', '价税合计', '状态', '提取时间'
        ]
        optional_fields = [
            '费用所属月份(审核月份)', '事业部', '大项目'
        ]
        conn = self.db_manager.get_connection()
        try:
            # 构造值元组，确保字段都存在
            values = (
                user_id,
                result.get('费用所属月份(审核月份)', '未选择'),
                result.get('事业部', '未选择'),
                result.get('大项目', '未选择'),
                result.get('文件名', '未命名'),
                result.get('姓名', '未知'),
                result.get('发票代码', ''),
                result.get('发票号码', ''),
                result.get('开票日期', ''),
                result.get('金额', 0),
                result.get('税率', 0),
                result.get('税额', 0),
                result.get('价税合计', 0),
                result.get('状态', '失败'),
                result.get('提取时间', datetime.datetime.now().isoformat())
            )
            conn.execute('''
                       INSERT INTO invoices (
                           user_id, shenheyuefen, shiyebu, daxiangmu, filename, person_name, invoice_code, invoice_number,
                           invoice_date, amount, tax_rate, tax_amount, total_amount, status, extracted_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ''', values)
            conn.commit()
            # logger.info("✅ 发票数据保存数据库成功")
        except Exception as e:
            logger.error(f"保存发票数据错误: {e}")
        finally:
            conn.close()

    def get_user_invoices(self, user_id: int, days: int = 30) -> List[Dict]:
        """获取用户发票数据"""
        conn = self.db_manager.get_connection()
        try:
            cursor = conn.execute('''
                SELECT * FROM invoices 
                WHERE user_id = ? AND date(created_at) >= date('now', ?) 
                ORDER BY created_at DESC
            ''', (user_id, f'-{days} days'))

            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取用户发票数据错误: {e}")
            return []
        finally:
            conn.close()

    def get_statistics(self, user_id: int) -> Dict:
        """获取统计信息"""
        conn = self.db_manager.get_connection()
        try:
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total_files,
                    SUM(CASE WHEN status = '成功' THEN 1 ELSE 0 END) as success_files,
                    SUM(amount) as total_amount,
                    SUM(tax_amount) as total_tax
                FROM invoices 
                WHERE user_id = ?
            ''', (user_id,))

            result = cursor.fetchone()
            if result:
                total_files, success_files, total_amount, total_tax = result
                success_rate = (success_files / total_files) * 100 if total_files > 0 else 0

                return {
                    '总文件数': total_files,
                    '成功数': success_files,
                    '失败数': total_files - success_files,
                    '总金额': total_amount or 0,
                    '总税额': total_tax or 0,
                    '总价税合计': (total_amount or 0) + (total_tax or 0),
                    '成功率': success_rate
                }
            return {}
        except Exception as e:
            logger.error(f"获取统计信息错误: {e}")
            return {}
        finally:
            conn.close()


class SystemService:
    """系统服务类"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_menu_functions(self) -> List[Dict]:
        """获取菜单功能列表"""
        conn = self.db_manager.get_connection()
        try:
            cursor = conn.execute('''
                SELECT function_name, icon, description 
                FROM menu_functions 
                WHERE is_active = 1 
                ORDER BY sort_order
            ''')
            return [dict(zip(['name', 'icon', 'description'], row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取菜单功能错误: {e}")
            return []
        finally:
            conn.close()

    def get_system_config(self, key: str = None) -> Dict:
        """获取系统配置"""
        conn = self.db_manager.get_connection()
        try:
            if key:
                cursor = conn.execute('SELECT config_key, config_value FROM system_config WHERE config_key = ?', (key,))
                result = cursor.fetchone()
                return {result[0]: result[1]} if result else {}
            else:
                cursor = conn.execute('SELECT config_key, config_value FROM system_config')
                return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"获取系统配置错误: {e}")
            return {}
        finally:
            conn.close()

    def log_operation(self, user_id: int, operation_type: str, detail: str, ip_address: str = ""):
        """记录操作日志"""
        conn = self.db_manager.get_connection()
        try:
            conn.execute('''
                INSERT INTO operation_logs (user_id, operation_type, operation_detail, ip_address)
                VALUES (?, ?, ?, ?)
            ''', (user_id, operation_type, detail, ip_address))
            conn.commit()
        except Exception as e:
            logger.error(f"记录操作日志错误: {e}")
        finally:
            conn.close()


class ExportService:
    """导出服务类"""

    @staticmethod
    def export_to_excel(invoices: List[Dict]) -> BytesIO:
        """导出到Excel"""
        df = pd.DataFrame(invoices)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='发票数据')
        output.seek(0)
        return output

    @staticmethod
    def export_to_csv(invoices: List[Dict]) -> str:
        """导出到CSV"""
        df = pd.DataFrame(invoices)
        return df.to_csv(index=False)

    @staticmethod
    def export_to_json(invoices: List[Dict]) -> str:
        """导出到JSON"""
        import json
        return json.dumps(invoices, ensure_ascii=False, indent=2)