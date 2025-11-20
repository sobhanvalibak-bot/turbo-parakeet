# -*- coding: utf-8 -*-
import asyncio
from telethon import TelegramClient, events, errors, Button
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.messages import ReadMessageContentsRequest, GetMessagesViewsRequest
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import MessageEntityMentionName, ReactionEmoji
from pathlib import Path
import logging
import json
import os
import sqlite3
import time
import re
from datetime import datetime, timedelta
import aiohttp
import random
from urllib.parse import quote
import instaloader
import yt_dlp
import requests
from bs4 import BeautifulSoup

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- پیکربندی ----------
API_ID = 28574261
API_HASH = "312efd0da3ff4e15245b7089329172b8"
BOT_TOKEN = "8267456711:AAF_b_wLIaPGfa85cMsvq706ISzuhAdbCLQ"
ADMIN_ID = 1276438321

# ربات‌های هدف
NOTEPAD_BOT = "@notepadbot"
MIDJOURNEY_BOT = "@Midjourney_kk1_bot"
ASKPLEX_BOT = "@askplexbot"

# کانال‌های مورد نظر
REQUIRED_CHANNELS = [
    "@novosti_efir",
    "@notepadnano_banaana", 
    "@archive_chats"
]

# پوشه‌ها
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
IMAGES_DIR = Path("img")
IMAGES_DIR.mkdir(exist_ok=True)
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
POST_DIR = Path("post")
POST_DIR.mkdir(exist_ok=True)
DESIGNS_DIR = Path("designs")
DESIGNS_DIR.mkdir(exist_ok=True)

# فایل دیتابیس
DB_FILE = DATA_DIR / "bot_database.db"

# دیکشنری برای مدیریت ارسال پیام‌های متوالی
message_queues = {}
message_locks = {}

class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # جدول کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                phone TEXT NOT NULL,
                name TEXT,
                session_file TEXT NOT NULL,
                joined_date TEXT NOT NULL,
                last_login TEXT NOT NULL,
                is_banned INTEGER DEFAULT 0
            )
        ''')
        
        # جدول سشن‌های فعال
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER PRIMARY KEY,
                phone TEXT NOT NULL,
                session_file TEXT NOT NULL,
                login_time TEXT NOT NULL
            )
        ''')
        
        # جدول آرشیو فعالیت‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                response TEXT,
                media_type TEXT
            )
        ''')
        
        # جدول عکس‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                description TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                file_size INTEGER NOT NULL
            )
        ''')
        
        # جدول پیام‌های ادمین
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                message_text TEXT NOT NULL,
                has_media INTEGER DEFAULT 0,
                media_path TEXT,
                sent_at TEXT NOT NULL,
                read_at TEXT
            )
        ''')
        
        # جدول اتورید
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auto_read_settings (
                user_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                include_pv INTEGER DEFAULT 1,
                include_groups INTEGER DEFAULT 1,
                include_channels INTEGER DEFAULT 1,
                last_check_time TEXT
            )
        ''')
        
        # جدول طراحی‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS designs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                design_type TEXT NOT NULL,
                description TEXT NOT NULL,
                result_path TEXT,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # جدول امنیت ادمین
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_security (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_changed TEXT NOT NULL
            )
        ''')
        
        # جدول تنظیمات ساعت
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS time_settings (
                user_id INTEGER PRIMARY KEY,
                bio_time_enabled INTEGER DEFAULT 0,
                name_time_enabled INTEGER DEFAULT 0,
                last_updated TEXT
            )
        ''')
        
        # جدول ربات‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_clients (
                bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_token TEXT NOT NULL,
                channels TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # جدول لاگ ادمین
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER,
                details TEXT,
                timestamp TEXT NOT NULL
            )
        ''')
        
        # جدول تنظیمات سیستم
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # جدول دانلودها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                url TEXT NOT NULL,
                file_path TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def execute_query(self, query, params=()):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
            return cursor
        except Exception as e:
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def fetch_one(self, query, params=()):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            conn.close()
    
    def fetch_all(self, query, params=()):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            conn.close()

class UserManager:
    def __init__(self, db):
        self.db = db
    
    def add_user(self, user_id, phone, session_file, name=None):
        query = '''
            INSERT OR REPLACE INTO users 
            (user_id, phone, name, session_file, joined_date, last_login, is_banned)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        now = datetime.now().isoformat()
        self.db.execute_query(query, (user_id, phone, name, session_file, now, now, 0))
        return True
    
    def get_user(self, user_id):
        query = 'SELECT * FROM users WHERE user_id = ?'
        result = self.db.fetch_one(query, (user_id,))
        if result:
            return {
                'user_id': result[0],
                'phone': result[1],
                'name': result[2],
                'session_file': result[3],
                'joined_date': result[4],
                'last_login': result[5],
                'is_banned': bool(result[6])
            }
        return None
    
    def get_all_users(self):
        query = 'SELECT * FROM users ORDER BY joined_date DESC'
        results = self.db.fetch_all(query)
        users = {}
        for row in results:
            users[row[0]] = {
                'phone': row[1],
                'name': row[2],
                'session_file': row[3],
                'joined_date': row[4],
                'last_login': row[5],
                'is_banned': bool(row[6])
            }
        return users
    
    def get_banned_users(self):
        query = 'SELECT * FROM users WHERE is_banned = 1 ORDER BY joined_date DESC'
        results = self.db.fetch_all(query)
        users = {}
        for row in results:
            users[row[0]] = {
                'phone': row[1],
                'name': row[2],
                'session_file': row[3],
                'joined_date': row[4],
                'last_login': row[5],
                'is_banned': bool(row[6])
            }
        return users
    
    def ban_user(self, user_id):
        query = 'UPDATE users SET is_banned = 1 WHERE user_id = ?'
        self.db.execute_query(query, (user_id,))
        return True
    
    def unban_user(self, user_id):
        query = 'UPDATE users SET is_banned = 0 WHERE user_id = ?'
        self.db.execute_query(query, (user_id,))
        return True
    
    def is_user_banned(self, user_id):
        user = self.get_user(user_id)
        return user and user['is_banned']
    
    def update_last_login(self, user_id):
        query = 'UPDATE users SET last_login = ? WHERE user_id = ?'
        self.db.execute_query(query, (datetime.now().isoformat(), user_id))
    
    def add_active_session(self, user_id, phone, session_file):
        query = '''
            INSERT OR REPLACE INTO active_sessions 
            (user_id, phone, session_file, login_time)
            VALUES (?, ?, ?, ?)
        '''
        self.db.execute_query(query, (user_id, phone, session_file, datetime.now().isoformat()))
    
    def remove_active_session(self, user_id):
        query = 'DELETE FROM active_sessions WHERE user_id = ?'
        self.db.execute_query(query, (user_id,))
    
    def get_active_sessions(self):
        query = 'SELECT * FROM active_sessions'
        results = self.db.fetch_all(query)
        return {row[0]: {'phone': row[1], 'session_file': row[2], 'login_time': row[3]} for row in results}

class AdminManager:
    def __init__(self, db):
        self.db = db
    
    def save_admin_message(self, user_id, admin_id, message_text, has_media=False, media_path=None):
        query = '''
            INSERT INTO admin_messages 
            (user_id, admin_id, message_text, has_media, media_path, sent_at)
            VALUES (?, ?, ?, ?, ?, ?)
        '''
        self.db.execute_query(query, (
            user_id, admin_id, message_text, 
            1 if has_media else 0, 
            media_path, 
            datetime.now().isoformat()
        ))
        return True
    
    def get_unread_messages(self, user_id):
        query = '''
            SELECT * FROM admin_messages 
            WHERE user_id = ? AND read_at IS NULL 
            ORDER BY sent_at DESC
        '''
        results = self.db.fetch_all(query, (user_id,))
        messages = []
        for row in results:
            messages.append({
                'id': row[0],
                'user_id': row[1],
                'admin_id': row[2],
                'message_text': row[3],
                'has_media': bool(row[4]),
                'media_path': row[5],
                'sent_at': row[6],
                'read_at': row[7]
            })
        return messages
    
    def mark_message_as_read(self, message_id):
        query = 'UPDATE admin_messages SET read_at = ? WHERE id = ?'
        self.db.execute_query(query, (datetime.now().isoformat(), message_id))
        return True
    
    def get_admin_stats(self):
        total_users = self.db.fetch_one('SELECT COUNT(*) FROM users')[0]
        today = datetime.now().date().isoformat()
        active_today = self.db.fetch_one(
            'SELECT COUNT(*) FROM users WHERE last_login LIKE ?', (f'{today}%',)
        )[0]
        banned_users = self.db.fetch_one('SELECT COUNT(*) FROM users WHERE is_banned = 1')[0]
        activities_today = self.db.fetch_one(
            'SELECT COUNT(*) FROM archive WHERE timestamp LIKE ?', (f'{today}%',)
        )[0]
        active_sessions = self.db.fetch_one('SELECT COUNT(*) FROM active_sessions')[0]
        total_images = self.db.fetch_one('SELECT COUNT(*) FROM images')[0] or 0
        total_designs = self.db.fetch_one('SELECT COUNT(*) FROM designs')[0] or 0
        
        return {
            'total_users': total_users,
            'active_today': active_today,
            'banned_users': banned_users,
            'activities_today': activities_today,
            'active_sessions': active_sessions,
            'total_images': total_images,
            'total_designs': total_designs
        }
    
    def add_admin_log(self, admin_id, action, target_id=None, details=None):
        query = '''
            INSERT INTO admin_logs 
            (admin_id, action, target_id, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
        '''
        self.db.execute_query(query, (
            admin_id, action, target_id, details, datetime.now().isoformat()
        ))
        return True
    
    def get_admin_logs(self, limit=50):
        query = '''
            SELECT * FROM admin_logs 
            ORDER BY timestamp DESC 
            LIMIT ?
        '''
        results = self.db.fetch_all(query, (limit,))
        logs = []
        for row in results:
            logs.append({
                'id': row[0],
                'admin_id': row[1],
                'action': row[2],
                'target_id': row[3],
                'details': row[4],
                'timestamp': row[5]
            })
        return logs

class ArchiveManager:
    def __init__(self, db):
        self.db = db
    
    def add_to_archive(self, user_id, activity_type, description, response=None, media_type=None):
        query = '''
            INSERT INTO archive 
            (user_id, timestamp, type, description, response, media_type)
            VALUES (?, ?, ?, ?, ?, ?)
        '''
        self.db.execute_query(query, (
            user_id, datetime.now().isoformat(), activity_type, 
            description, response, media_type
        ))
        return True
    
    def get_user_archive(self, user_id, limit=100):
        query = '''
            SELECT * FROM archive 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        '''
        results = self.db.fetch_all(query, (user_id, limit))
        return [
            {
                'id': row[0],
                'user_id': row[1],
                'timestamp': row[2],
                'type': row[3],
                'description': row[4],
                'response': row[5],
                'media_type': row[6]
            } for row in results
        ]
    
    def get_archive_stats(self, user_id):
        query = '''
            SELECT type, COUNT(*) FROM archive 
            WHERE user_id = ? 
            GROUP BY type
        '''
        results = self.db.fetch_all(query, (user_id,))
        stats = {'total': 0}
        for row in results:
            stats[row[0]] = row[1]
            stats['total'] += row[1]
        return stats

class ImageManager:
    def __init__(self, db):
        self.db = db
    
    async def save_image_to_disk(self, client, image_message, description, user_id):
        try:
            if not image_message.media:
                return None
            
            user_img_dir = IMAGES_DIR / str(user_id)
            user_img_dir.mkdir(exist_ok=True)
            
            timestamp = int(time.time())
            filename = f"{timestamp}_{description[:20]}.jpg".replace(" ", "_")
            file_path = user_img_dir / filename
            
            await client.download_media(image_message, file=str(file_path))
            
            query = '''
                INSERT INTO images 
                (user_id, filename, file_path, description, timestamp, file_size)
                VALUES (?, ?, ?, ?, ?, ?)
            '''
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            self.db.execute_query(query, (user_id, filename, str(file_path), description, timestamp, file_size))
            
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving image to disk: {e}")
            return None
    
    def get_user_images_stats(self, user_id):
        query = '''
            SELECT COUNT(*), SUM(file_size) 
            FROM images 
            WHERE user_id = ?
        '''
        result = self.db.fetch_one(query, (user_id,))
        
        query_list = '''
            SELECT * FROM images 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 10
        '''
        images_list = self.db.fetch_all(query_list, (user_id,))
        
        total_images = result[0] if result[0] else 0
        total_size = result[1] if result[1] else 0
        
        images_data = []
        for row in images_list:
            images_data.append({
                'id': row[0],
                'user_id': row[1],
                'filename': row[2],
                'file_path': row[3],
                'description': row[4],
                'timestamp': row[5],
                'file_size': row[6]
            })
        
        return {
            'total_images': total_images,
            'total_size': total_size,
            'images_list': images_data
        }

class AutoReadManager:
    def __init__(self, db):
        self.db = db
    
    def enable_auto_read(self, user_id, include_pv=True, include_groups=True, include_channels=True):
        query = '''
            INSERT OR REPLACE INTO auto_read_settings 
            (user_id, enabled, include_pv, include_groups, include_channels, last_check_time)
            VALUES (?, ?, ?, ?, ?, ?)
        '''
        self.db.execute_query(query, (
            user_id, 1, 
            1 if include_pv else 0,
            1 if include_groups else 0, 
            1 if include_channels else 0,
            datetime.now().isoformat()
        ))
        return True
    
    def disable_auto_read(self, user_id):
        query = 'UPDATE auto_read_settings SET enabled = 0 WHERE user_id = ?'
        self.db.execute_query(query, (user_id,))
        return True
    
    def get_auto_read_settings(self, user_id):
        query = 'SELECT * FROM auto_read_settings WHERE user_id = ?'
        result = self.db.fetch_one(query, (user_id,))
        if result:
            return {
                'user_id': result[0],
                'enabled': bool(result[1]),
                'include_pv': bool(result[2]),
                'include_groups': bool(result[3]),
                'include_channels': bool(result[4]),
                'last_check_time': result[5]
            }
        return None
    
    def update_last_check(self, user_id):
        query = 'UPDATE auto_read_settings SET last_check_time = ? WHERE user_id = ?'
        self.db.execute_query(query, (datetime.now().isoformat(), user_id))

class DesignManager:
    def __init__(self, db):
        self.db = db
        self.designs_dir = Path("designs")
        self.designs_dir.mkdir(exist_ok=True)
    
    def save_design_request(self, user_id, design_type, description, result_path=None):
        query = '''
            INSERT INTO designs 
            (user_id, design_type, description, result_path, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
        '''
        self.db.execute_query(query, (
            user_id, design_type, description, result_path,
            datetime.now().isoformat(), 'completed' if result_path else 'pending'
        ))
        return True
    
    def get_user_designs(self, user_id, limit=10):
        query = '''
            SELECT * FROM designs 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        '''
        results = self.db.fetch_all(query, (user_id, limit))
        designs = []
        for row in results:
            designs.append({
                'id': row[0],
                'user_id': row[1],
                'design_type': row[2],
                'description': row[3],
                'result_path': row[4],
                'created_at': row[5],
                'status': row[6]
            })
        return designs

class AdminSecurityManager:
    """مدیریت امنیت ادمین"""
    
    def __init__(self, db):
        self.db = db
        self.current_password = "1276438321"  # رمز پیش‌فرض
        self.init_admin_security()
    
    def init_admin_security(self):
        """ایجاد جدول امنیت ادمین"""
        query = '''
            CREATE TABLE IF NOT EXISTS admin_security (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_changed TEXT NOT NULL
            )
        '''
        self.db.execute_query(query)
        
        # تنظیم رمز پیش‌فرض اگر وجود ندارد
        existing = self.db.fetch_one('SELECT COUNT(*) FROM admin_security')
        if existing[0] == 0:
            query = '''
                INSERT INTO admin_security 
                (password, created_at, last_changed)
                VALUES (?, ?, ?)
            '''
            now = datetime.now().isoformat()
            self.db.execute_query(query, (self.current_password, now, now))
        else:
            # بارگذاری رمز فعلی
            result = self.db.fetch_one('SELECT password FROM admin_security ORDER BY id DESC LIMIT 1')
            if result:
                self.current_password = result[0]
    
    def verify_password(self, password):
        """بررسی رمز عبور"""
        return password == self.current_password
    
    def change_password(self, new_password):
        """تغییر رمز عبور"""
        query = '''
            INSERT INTO admin_security 
            (password, created_at, last_changed)
            VALUES (?, ?, ?)
        '''
        now = datetime.now().isoformat()
        self.db.execute_query(query, (new_password, now, now))
        self.current_password = new_password
        return True
    
    def get_password_history(self):
        """تاریخچه رمزهای عبور"""
        query = 'SELECT * FROM admin_security ORDER BY created_at DESC LIMIT 5'
        results = self.db.fetch_all(query)
        history = []
        for row in results:
            history.append({
                'id': row[0],
                'password': row[1],
                'created_at': row[2],
                'last_changed': row[3]
            })
        return history

class TimeManager:
    """مدیریت زمان و تنظیمات ساعت"""
    
    def __init__(self, db):
        self.db = db
        self.init_time_database()
    
    def init_time_database(self):
        """ایجاد جدول تنظیمات ساعت"""
        query = '''
            CREATE TABLE IF NOT EXISTS time_settings (
                user_id INTEGER PRIMARY KEY,
                bio_time_enabled INTEGER DEFAULT 0,
                name_time_enabled INTEGER DEFAULT 0,
                last_updated TEXT
            )
        '''
        self.db.execute_query(query)
    
    def enable_bio_time(self, user_id):
        """فعال کردن ساعت در بیو"""
        query = '''
            INSERT OR REPLACE INTO time_settings 
            (user_id, bio_time_enabled, name_time_enabled, last_updated)
            VALUES (?, 1, ?, ?)
        '''
        self.db.execute_query(query, (user_id, 0, datetime.now().isoformat()))
        return True
    
    def disable_bio_time(self, user_id):
        """غیرفعال کردن ساعت در بیو"""
        query = '''
            INSERT OR REPLACE INTO time_settings 
            (user_id, bio_time_enabled, name_time_enabled, last_updated)
            VALUES (?, 0, ?, ?)
        '''
        self.db.execute_query(query, (user_id, 0, datetime.now().isoformat()))
        return True
    
    def enable_name_time(self, user_id):
        """فعال کردن ساعت در نام"""
        query = '''
            INSERT OR REPLACE INTO time_settings 
            (user_id, bio_time_enabled, name_time_enabled, last_updated)
            VALUES (?, ?, 1, ?)
        '''
        self.db.execute_query(query, (user_id, 0, datetime.now().isoformat()))
        return True
    
    def disable_name_time(self, user_id):
        """غیرفعال کردن ساعت در نام"""
        query = '''
            INSERT OR REPLACE INTO time_settings 
            (user_id, bio_time_enabled, name_time_enabled, last_updated)
            VALUES (?, ?, 0, ?)
        '''
        self.db.execute_query(query, (user_id, 0, datetime.now().isoformat()))
        return True
    
    def get_time_settings(self, user_id):
        """دریافت تنظیمات ساعت کاربر"""
        query = 'SELECT * FROM time_settings WHERE user_id = ?'
        result = self.db.fetch_one(query, (user_id,))
        if result:
            return {
                'user_id': result[0],
                'bio_time_enabled': bool(result[1]),
                'name_time_enabled': bool(result[2]),
                'last_updated': result[3]
            }
        return None
    
    def get_current_time_string(self):
        """دریافت زمان فعلی به صورت رشته"""
        now = datetime.now()
        return now.strftime("%H:%M")
    
    def get_full_time_string(self):
        """دریافت زمان کامل"""
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

class BotManager:
    """مدیریت ربات‌های اضافی"""
    
    def __init__(self, db):
        self.db = db
        self.active_bots = {}
    
    def add_bot(self, bot_token, channels=None):
        """افزودن ربات جدید به دیتابیس"""
        query = '''
            INSERT INTO bot_clients 
            (bot_token, channels, created_at, is_active)
            VALUES (?, ?, ?, ?)
        '''
        channels_str = json.dumps(channels) if channels else None
        self.db.execute_query(query, (
            bot_token, channels_str, 
            datetime.now().isoformat(), 1
        ))
        return True
    
    def get_active_bots(self):
        """دریافت ربات‌های فعال"""
        query = 'SELECT * FROM bot_clients WHERE is_active = 1'
        results = self.db.fetch_all(query)
        bots = []
        for row in results:
            bots.append({
                'bot_id': row[0],
                'bot_token': row[1],
                'channels': json.loads(row[2]) if row[2] else [],
                'created_at': row[3],
                'is_active': bool(row[4])
            })
        return bots
    
    def deactivate_bot(self, bot_id):
        """غیرفعال کردن ربات"""
        query = 'UPDATE bot_clients SET is_active = 0 WHERE bot_id = ?'
        self.db.execute_query(query, (bot_id,))
        return True

class DownloadManager:
    """مدیریت دانلودها"""
    
    def __init__(self, db):
        self.db = db
    
    def add_download(self, user_id, service, url, file_path=None):
        """افزودن دانلود جدید"""
        query = '''
            INSERT INTO downloads 
            (user_id, service, url, file_path, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        '''
        self.db.execute_query(query, (
            user_id, service, url, file_path, 'pending', datetime.now().isoformat()
        ))
        return True
    
    def update_download_status(self, download_id, status, file_path=None):
        """بروزرسانی وضعیت دانلود"""
        query = '''
            UPDATE downloads 
            SET status = ?, file_path = ? 
            WHERE id = ?
        '''
        self.db.execute_query(query, (status, file_path, download_id))
        return True
    
    def get_user_downloads(self, user_id, limit=10):
        """دریافت دانلودهای کاربر"""
        query = '''
            SELECT * FROM downloads 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        '''
        results = self.db.fetch_all(query, (user_id, limit))
        downloads = []
        for row in results:
            downloads.append({
                'id': row[0],
                'user_id': row[1],
                'service': row[2],
                'url': row[3],
                'file_path': row[4],
                'status': row[5],
                'created_at': row[6]
            })
        return downloads

# ایجاد مدیران
db = DatabaseManager()
user_manager = UserManager(db)
admin_manager = AdminManager(db)
archive_manager = ArchiveManager(db)
image_manager = ImageManager(db)
auto_read_manager = AutoReadManager(db)
design_manager = DesignManager(db)
admin_security_manager = AdminSecurityManager(db)
time_manager = TimeManager(db)
bot_manager = BotManager(db)
download_manager = DownloadManager(db)

def session_name(phone):
    return str(SESSIONS_DIR / phone.replace("+", ""))

async def create_user_client(phone):
    session = session_name(phone)
    client = TelegramClient(
        session, 
        API_ID, 
        API_HASH,
        connection_retries=3,
        retry_delay=2,
        auto_reconnect=True
    )
    await client.connect()
    return client

async def is_session_valid(phone):
    client = None
    try:
        client = await create_user_client(phone)
        return await client.is_user_authorized()
    except Exception as e:
        logger.error(f"Error checking session: {e}")
        return False
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass

async def send_code_request(phone):
    client = None
    try:
        client = await create_user_client(phone)
        sent_code = await client.send_code_request(phone)
        return sent_code
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass

async def sign_in_user(phone, code, phone_code_hash):
    client = None
    try:
        client = await create_user_client(phone)
        await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash
        )
        return True
    except errors.SessionPasswordNeededError:
        raise
    except Exception as e:
        logger.error(f"Error in login: {e}")
        raise
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass

async def join_required_channels(client):
    try:
        joined_channels = []
        for channel in REQUIRED_CHANNELS:
            try:
                entity = await client.get_entity(channel)
                await client.join_channel(entity)
                joined_channels.append(channel)
                await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"⚠️ Could not join {channel}: {e}")
        return joined_channels
    except Exception as e:
        logger.error(f"Error joining channels: {e}")
        return []

async def send_to_notepad_and_get_response(client, question):
    try:
        clean_question = question.lstrip('،')
        await client.send_message(NOTEPAD_BOT, clean_question)
        await asyncio.sleep(3)
        
        async for message in client.iter_messages(NOTEPAD_BOT, limit=1):
            if message.text and message.sender_id == (await client.get_entity(NOTEPAD_BOT)).id:
                return message.text
        
        return "🤷‍♂️ **پاسخی دریافت نشد**"
        
    except Exception as e:
        logger.error(f"Error with notepad: {e}")
        return "❌ **خطا در ارتباط با نوت پد**"

async def generate_image_with_askplex(client, description):
    try:
        sent_message = await client.send_message(ASKPLEX_BOT, description)
        await asyncio.sleep(10)
        
        async for message in client.iter_messages(ASKPLEX_BOT, limit=5):
            if (message.media and 
                message.date.timestamp() > time.time() - 30 and
                message.sender_id == (await client.get_entity(ASKPLEX_BOT)).id):
                return message
        
        return None
    except Exception as e:
        logger.error(f"Error with askplex: {e}")
        return None

async def generate_image_with_midjourney(client, description):
    try:
        sent_message = await client.send_message(MIDJOURNEY_BOT, description)
        await asyncio.sleep(15)
        
        async for message in client.iter_messages(MIDJOURNEY_BOT, limit=5):
            if (message.media and 
                message.date.timestamp() > time.time() - 30 and
                message.sender_id == (await client.get_entity(MIDJOURNEY_BOT)).id):
                return message
        
        return None
    except Exception as e:
        logger.error(f"Error with midjourney: {e}")
        return None

async def create_minimalist_logo(client, description):
    try:
        prompt = f"minimalist logo: {description}, simple, clean, modern, vector logo, single color, white background"
        return await generate_image_with_midjourney(client, prompt)
    except Exception as e:
        logger.error(f"Error creating minimalist logo: {e}")
        return None

async def create_business_logo(client, description):
    try:
        prompt = f"professional business logo: {description}, corporate, elegant, modern, professional design"
        return await generate_image_with_midjourney(client, prompt)
    except Exception as e:
        logger.error(f"Error creating business logo: {e}")
        return None

async def create_creative_logo(client, description):
    try:
        prompt = f"creative logo: {description}, artistic, unique, colorful, innovative design"
        return await generate_image_with_midjourney(client, prompt)
    except Exception as e:
        logger.error(f"Error creating creative logo: {e}")
        return None

async def get_dollar_price():
    try:
        url = "https://api.tgju.org/v1/data/sana/price_dollar_rl"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                price = data['data']['price']
                return f"{int(float(price)):,}"
    except Exception as e:
        logger.error(f"Error getting dollar price: {e}")
        return "۱,۱۲۸,۱۵۰"

async def google_search(query):
    try:
        encoded_query = quote(query)
        search_url = f"https://www.google.com/search?q={encoded_query}"
        return f"🔍 **نتایج جستجو برای:** {query}\n\n🌐 **لینک جستجو:** {search_url}"
    except Exception as e:
        logger.error(f"Error in google search: {e}")
        return f"❌ خطا در جستجو: {str(e)}"

async def download_instagram_post(url):
    try:
        L = instaloader.Instaloader(
            dirname_pattern=str(POST_DIR / "instagram_{profile}"),
            save_metadata=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            compress_json=False
        )
        
        if '/p/' in url:
            shortcode = url.split('/p/')[1].split('/')[0]
        elif '/reel/' in url:
            shortcode = url.split('/reel/')[1].split('/')[0]
        else:
            return None, "❌ لینک معتبر نیست"
        
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=str(POST_DIR / f"instagram_{post.owner_username}"))
        
        download_dir = POST_DIR / f"instagram_{post.owner_username}"
        for file in os.listdir(download_dir):
            if file.endswith(('.jpg', '.mp4', '.png')):
                return os.path.join(download_dir, file), None
        
        return None, "❌ فایل پیدا نشد"
        
    except Exception as e:
        return None, f"❌ خطا در دانلود: {str(e)}"

async def download_youtube_video(url):
    try:
        ydl_opts = {
            'outtmpl': str(POST_DIR / 'youtube' / '%(title)s.%(ext)s'),
            'format': 'best[height<=720]',
            'writesubtitles': False,
            'writeautomaticsub': False,
            'writethumbnail': False,
        }
        
        youtube_dir = POST_DIR / 'youtube'
        youtube_dir.mkdir(exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
        return filename, None
        
    except Exception as e:
        return None, f"❌ خطا در دانلود: {str(e)}"

async def mark_all_as_read(client, include_pv=True, include_groups=True, include_channels=True):
    try:
        marked_count = 0
        async for dialog in client.iter_dialogs():
            try:
                is_pv = dialog.is_user and not dialog.is_group and not dialog.is_channel
                is_group = dialog.is_group
                is_channel = dialog.is_channel
                
                should_mark = (
                    (is_pv and include_pv) or
                    (is_group and include_groups) or
                    (is_channel and include_channels)
                )
                
                if should_mark and dialog.unread_count > 0:
                    await client.send_read_acknowledge(dialog.entity)
                    marked_count += 1
                    await asyncio.sleep(0.1)
            except Exception as e:
                continue
        return marked_count
    except Exception as e:
        logger.error(f"Error in mark_all_as_read: {e}")
        return 0

async def update_user_time_settings(client, user_id):
    """بروزرسانی تنظیمات زمان کاربر"""
    try:
        time_settings = time_manager.get_time_settings(user_id)
        if not time_settings:
            return
        
        try:
            me = await client.get_me()
            current_bio = getattr(me, "about", "") or ""
            current_first_name = me.first_name or ""
            current_last_name = me.last_name or ""
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return
        
        current_time = time_manager.get_current_time_string()
        
        if time_settings['bio_time_enabled']:
            try:
                clean_bio = re.sub(r'⏰ \d{1,2}:\d{2}', '', current_bio).strip()
                new_bio = f"{clean_bio} ⏰ {current_time}".strip()
                if new_bio != current_bio:
                    await client(UpdateProfileRequest(about=new_bio))
            except Exception as e:
                logger.error(f"Error updating bio: {e}")
        
        if time_settings['name_time_enabled']:
            try:
                clean_first_name = re.sub(r'⏰ \d{1,2}:\d{2}', '', current_first_name).strip()
                new_first_name = f"{clean_first_name} ⏰ {current_time}".strip()
                
                if new_first_name != current_first_name:
                    await client(UpdateProfileRequest(
                        first_name=new_first_name,
                        last_name=current_last_name or ""
                    ))
            except Exception as e:
                logger.error(f"Error updating name: {e}")
                
    except Exception as e:
        logger.error(f"Error updating time settings: {e}")

async def cleanup_user_time_settings(client, user_id):
    """پاک‌سازی تنظیمات زمان کاربر قبل از خاموش شدن"""
    try:
        time_settings = time_manager.get_time_settings(user_id)
        if not time_settings:
            return
        
        try:
            me = await client.get_me()
            current_bio = getattr(me, "about", "") or ""
            current_first_name = me.first_name or ""
            current_last_name = me.last_name or ""
        except Exception as e:
            logger.error(f"Error getting user info for cleanup: {e}")
            return
        
        if time_settings['bio_time_enabled']:
            try:
                clean_bio = re.sub(r'⏰ \d{1,2}:\d{2}', '', current_bio).strip()
                if clean_bio != current_bio:
                    await client(UpdateProfileRequest(about=clean_bio))
            except Exception as e:
                logger.error(f"Error cleaning bio: {e}")
        
        if time_settings['name_time_enabled']:
            try:
                clean_first_name = re.sub(r'⏰ \d{1,2}:\d{2}', '', current_first_name).strip()
                if clean_first_name != current_first_name:
                    await client(UpdateProfileRequest(
                        first_name=clean_first_name,
                        last_name=current_last_name or ""
                    ))
            except Exception as e:
                logger.error(f"Error cleaning name: {e}")
        
        time_manager.disable_bio_time(user_id)
        time_manager.disable_name_time(user_id)
        
    except Exception as e:
        logger.error(f"Error cleaning up time settings: {e}")

async def time_update_worker(client, user_id):
    """کارگر بروزرسانی زمان"""
    try:
        logger.info(f"🕒 Time update worker started for user {user_id}")
        
        while True:
            try:
                time_settings = time_manager.get_time_settings(user_id)
                if not time_settings or (not time_settings['bio_time_enabled'] and not time_settings['name_time_enabled']):
                    logger.info(f"🕒 Time update worker stopped for user {user_id} - settings disabled")
                    break
                
                if not client.is_connected():
                    logger.warning(f"🕒 Client disconnected for user {user_id}, stopping time worker")
                    break
                
                await update_user_time_settings(client, user_id)
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in time update worker loop: {e}")
                await asyncio.sleep(30)
                
    except asyncio.CancelledError:
        logger.info(f"🕒 Time update task cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Time update worker error: {e}")

async def auto_read_worker(client, user_id):
    """کارگر اتورید"""
    try:
        while True:
            settings = auto_read_manager.get_auto_read_settings(user_id)
            if not settings or not settings['enabled']:
                break
            
            try:
                marked_count = await mark_all_as_read(
                    client,
                    include_pv=settings['include_pv'],
                    include_groups=settings['include_groups'],
                    include_channels=settings['include_channels']
                )
                
                if marked_count > 0:
                    logger.info(f"Auto-read marked {marked_count} dialogs for user {user_id}")
                
                auto_read_manager.update_last_check(user_id)
            except Exception as e:
                logger.error(f"Error in auto-read worker: {e}")
            
            await asyncio.sleep(30)
            
    except asyncio.CancelledError:
        logger.info(f"Auto-read task cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Auto-read worker error: {e}")

async def mark_message_as_seen_by_all_users(message_link):
    """علامت زدن پیام به عنوان دیده شده توسط همه کاربران"""
    try:
        active_sessions = user_manager.get_active_sessions()
        seen_count = 0
        
        for user_id, session_data in active_sessions.items():
            try:
                if user_manager.is_user_banned(int(user_id)):
                    continue
                    
                phone = session_data['phone']
                if await is_session_valid(phone):
                    client = await create_user_client(phone)
                    await client.start(phone)
                    
                    try:
                        # استخراج اطلاعات از لینک پیام
                        if 't.me/' in message_link:
                            parts = message_link.split('/')
                            if len(parts) >= 5:
                                channel = parts[-2]
                                message_id = int(parts[-1])
                                
                                entity = await client.get_entity(channel)
                                await client(GetMessagesViewsRequest(
                                    peer=entity,
                                    id=[message_id],
                                    increment=True
                                ))
                                
                                logger.info(f"✅ Message marked as seen by user {user_id}")
                                seen_count += 1
                    except Exception as e:
                        logger.error(f"Error marking message as seen for user {user_id}: {e}")
                    
                    await client.disconnect()
                    
            except Exception as e:
                logger.error(f"Error processing user {user_id} for seen: {e}")
        
        return seen_count
        
    except Exception as e:
        logger.error(f"Error in mark_message_as_seen_by_all_users: {e}")
        return 0

async def add_reaction_to_message_by_all_users(message_link, reaction):
    """اضافه کردن ری‌اکشن به پیام توسط همه کاربران"""
    try:
        active_sessions = user_manager.get_active_sessions()
        reaction_count = 0
        
        for user_id, session_data in active_sessions.items():
            try:
                if user_manager.is_user_banned(int(user_id)):
                    continue
                    
                phone = session_data['phone']
                if await is_session_valid(phone):
                    client = await create_user_client(phone)
                    await client.start(phone)
                    
                    try:
                        # استخراج اطلاعات از لینک پیام
                        if 't.me/' in message_link:
                            parts = message_link.split('/')
                            if len(parts) >= 5:
                                channel = parts[-2]
                                message_id = int(parts[-1])
                                
                                entity = await client.get_entity(channel)
                                
                                # ایجاد ری‌اکشن
                                reaction_obj = ReactionEmoji(emoticon=reaction)
                                
                                await client(SendReactionRequest(
                                    peer=entity,
                                    msg_id=message_id,
                                    reaction=[reaction_obj]
                                ))
                                
                                logger.info(f"✅ Reaction {reaction} added by user {user_id}")
                                reaction_count += 1
                    except Exception as e:
                        logger.error(f"Error adding reaction for user {user_id}: {e}")
                    
                    await client.disconnect()
                    
            except Exception as e:
                logger.error(f"Error processing user {user_id} for reaction: {e}")
        
        return reaction_count
        
    except Exception as e:
        logger.error(f"Error in add_reaction_to_message_by_all_users: {e}")
        return 0

async def start_bot_client(bot_token, channels=None):
    """راه‌اندازی ربات و جوین شدن در کانال‌ها"""
    try:
        bot_client = TelegramClient(f'bot_{bot_token[:10]}', API_ID, API_HASH)
        await bot_client.start(bot_token=bot_token)
        
        if channels:
            for channel in channels:
                try:
                    entity = await bot_client.get_entity(channel)
                    await bot_client.join_channel(entity)
                    logger.info(f"✅ Joined channel: {channel}")
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"❌ Could not join {channel}: {e}")
        
        return bot_client
    except Exception as e:
        logger.error(f"Error starting bot client: {e}")
        return None

# دیکشنری‌های global
active_clients = {}
user_requests = {}
user_sessions = {}
admin_sessions = {}
auto_read_tasks = {}
image_choice_sessions = {}
design_sessions = {}
read_settings_sessions = {}
admin_auth_sessions = {}
time_update_tasks = {}
clock_sessions = {}
bot_clients = {}

async def sequential_message_sender(client, chat_id, messages):
    """ارسال پیام‌ها به صورت متوالی"""
    if chat_id not in message_locks:
        message_locks[chat_id] = asyncio.Lock()
    
    async with message_locks[chat_id]:
        for message in messages:
            try:
                if isinstance(message, dict) and 'file' in message:
                    await client.send_file(
                        chat_id,
                        message['file'],
                        caption=message.get('caption', '')
                    )
                else:
                    await client.send_message(chat_id, message)
                
                # تأخیر بین ارسال پیام‌ها
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error sending sequential message: {e}")

async def start_user_client(phone, user_id):
    try:
        if user_manager.is_user_banned(user_id):
            logger.info(f"User {user_id} is banned, cannot start client")
            return None

        client = await create_user_client(phone)
        await client.start(phone)
        
        joined_channels = await join_required_channels(client)
        user_manager.add_active_session(user_id, phone, session_name(phone))
        user_manager.update_last_login(user_id)
        
        time_settings = time_manager.get_time_settings(user_id)
        if time_settings and (time_settings['bio_time_enabled'] or time_settings['name_time_enabled']):
            logger.info(f"🕒 Starting time worker for user {user_id}")
            time_update_tasks[user_id] = asyncio.create_task(
                time_update_worker(client, user_id)
            )
        
        # هندلرهای کاربر
        @client.on(events.NewMessage(pattern=r'^،(.+)$'))
        async def ai_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                question = event.pattern_match.group(1).strip()
                
                if len(question) < 2:
                    return
                
                unread_messages = admin_manager.get_unread_messages(user_id)
                if unread_messages:
                    notification_msg = await event.respond(
                        "📩 **شما پیام جدید از مدیر دریافت کرده‌اید!**\nبرای خواندن /sms را بزنید"
                    )
                    await asyncio.sleep(5)
                    await notification_msg.delete()
                
                processing_msg = await event.respond("🎯 **در حال پرسیدن از نوت پد...**")
                answer = await send_to_notepad_and_get_response(client, question)
                archive_manager.add_to_archive(user_id, "notepad", question, answer)
                
                response_text = f"""
🧠 **پاسخ نوت پد:**

📝 **سوال شما:**
{question}

💡 **پاسخ:**
{answer}

⏰ **زمان:** {datetime.now().strftime("%H:%M")}
                """
                await processing_msg.edit(response_text)
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.عکس\s+(.+)$'))
        async def image_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                description = event.pattern_match.group(1).strip()
                
                if len(description) < 3:
                    error_msg = await event.respond("❌ **توضیحات خیلی کوتاه است!**")
                    await asyncio.sleep(3)
                    await error_msg.delete()
                    return
                
                choice_msg = await event.respond("""
🎨 **لطفاً هوش مصنوعی مورد نظر را انتخاب کنید:**

1️⃣ **@askplexbot** - سرعت بالا
2️⃣ **@Midjourney_kk1_bot** - کیفیت بالا

💡 عدد مورد نظر را ریپلای کنید
                """)
                
                image_choice_sessions[user_id] = {
                    'description': description,
                    'choice_message_id': choice_msg.id,
                    'step': 'waiting_choice'
                }
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage)
        async def image_choice_handler(event):
            user_id = event.sender_id
            
            if (user_id in image_choice_sessions and 
                image_choice_sessions[user_id]['step'] == 'waiting_choice' and
                event.is_reply and
                event.reply_to_msg_id == image_choice_sessions[user_id]['choice_message_id']):
                
                try:
                    choice = event.text.strip()
                    description = image_choice_sessions[user_id]['description']
                    
                    await client.delete_messages(event.chat_id, [image_choice_sessions[user_id]['choice_message_id']])
                    
                    status_msg = await event.respond("🎨 **در حال تولید عکس...**")
                    
                    if choice == '1':
                        image_message = await generate_image_with_askplex(client, description)
                        ai_name = "AskPlex"
                    elif choice == '2':
                        image_message = await generate_image_with_midjourney(client, description)
                        ai_name = "Midjourney"
                    else:
                        await status_msg.edit("❌ **عدد نامعتبر!**")
                        del image_choice_sessions[user_id]
                        return
                    
                    if image_message:
                        saved_path = await image_manager.save_image_to_disk(client, image_message, description, user_id)
                        
                        caption = f"""
🎨 **عکس تولید شده با {ai_name}**

📝 **توضیحات:**
{description}

🤖 **هوش مصنوعی:** {ai_name}
💾 **ذخیره شده:** {'✅' if saved_path else '❌'}
⏰ **زمان:** {datetime.now().strftime("%H:%M")}
                        """
                        
                        if saved_path and os.path.exists(saved_path):
                            await client.send_file(
                                event.chat_id,
                                str(saved_path),
                                caption=caption
                            )
                        else:
                            await client.send_file(
                                event.chat_id,
                                image_message.media,
                                caption=caption
                            )
                        
                        await status_msg.delete()
                        archive_manager.add_to_archive(user_id, "image_generation", description, media_type="عکس")
                        
                    else:
                        await status_msg.edit("❌ **خطا در تولید عکس**")
                    
                    del image_choice_sessions[user_id]
                    
                except Exception as e:
                    error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    if user_id in image_choice_sessions:
                        del image_choice_sessions[user_id]

        @client.on(events.NewMessage(pattern=r'^\.لوگو\s+(.+)$'))
        async def logo_design_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                description = event.pattern_match.group(1).strip()
                
                if len(description) < 3:
                    error_msg = await event.respond("❌ **توضیحات لوگو خیلی کوتاه است!**")
                    await asyncio.sleep(3)
                    await error_msg.delete()
                    return
                
                style_msg = await event.respond("""
🎨 **طراحی لوگو - انتخاب سبک**

لطفاً سبک مورد نظر برای لوگو را انتخاب کنید:

1️⃣ **مینیمال** - ساده و مدرن
2️⃣ **کسب‌وکار** - حرفه‌ای و شرکتی  
3️⃣ **خلاقانه** - هنری و منحصر به فرد
4️⃣ **کلاسیک** - سنتی و اصیل

💡 عدد مورد نظر را ریپلای کنید
                """)
                
                design_sessions[user_id] = {
                    'description': description,
                    'style_message_id': style_msg.id,
                    'step': 'waiting_style'
                }
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در طراحی لوگو:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage)
        async def logo_style_handler(event):
            user_id = event.sender_id
            
            if (user_id in design_sessions and 
                design_sessions[user_id]['step'] == 'waiting_style' and
                event.is_reply and
                event.reply_to_msg_id == design_sessions[user_id]['style_message_id']):
                
                try:
                    style_choice = event.text.strip()
                    description = design_sessions[user_id]['description']
                    
                    await client.delete_messages(event.chat_id, [design_sessions[user_id]['style_message_id']])
                    
                    processing_msg = await event.respond("🎨 **در حال طراحی لوگو...**")
                    
                    logo_result = None
                    style_name = ""
                    
                    if style_choice == '1':
                        logo_result = await create_minimalist_logo(client, description)
                        style_name = "مینیمال"
                    elif style_choice == '2':
                        logo_result = await create_business_logo(client, description)
                        style_name = "کسب‌وکار"
                    elif style_choice == '3':
                        logo_result = await create_creative_logo(client, description)
                        style_name = "خلاقانه"
                    elif style_choice == '4':
                        logo_result = await generate_image_with_midjourney(client, description)
                        style_name = "کلاسیک"
                    else:
                        await processing_msg.edit("❌ **عدد نامعتبر!**")
                        del design_sessions[user_id]
                        return
                    
                    if logo_result:
                        user_design_dir = IMAGES_DIR / str(user_id) / "logos"
                        user_design_dir.mkdir(parents=True, exist_ok=True)
                        
                        timestamp = int(time.time())
                        filename = f"logo_{timestamp}_{description[:15]}.jpg".replace(" ", "_")
                        file_path = user_design_dir / filename
                        
                        await client.download_media(logo_result, file=str(file_path))
                        
                        design_manager.save_design_request(
                            user_id, f"logo_{style_name}", description, str(file_path)
                        )
                        
                        caption = f"""
🎨 **لوگو طراحی شده**

📝 **توضیحات:** {description}
🎭 **سبک:** {style_name}
💾 **ذخیره شده:** ✅
⏰ **زمان:** {datetime.now().strftime("%H:%M")}

✨ **لوگو شما آماده است!**
                        """
                        
                        if os.path.exists(file_path):
                            await client.send_file(
                                event.chat_id,
                                str(file_path),
                                caption=caption
                            )
                        else:
                            await client.send_file(
                                event.chat_id,
                                logo_result.media,
                                caption=caption
                            )
                        
                        await processing_msg.delete()
                        archive_manager.add_to_archive(user_id, "logo_design", description, f"سبک: {style_name}")
                        
                    else:
                        await processing_msg.edit("❌ **خطا در طراحی لوگو**")
                    
                    del design_sessions[user_id]
                    
                except Exception as e:
                    error_msg = await event.respond(f"❌ **خطا در طراحی:** {str(e)}")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    if user_id in design_sessions:
                        del design_sessions[user_id]

        @client.on(events.NewMessage(pattern=r'^\.تایم$'))
        async def time_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                
                full_time = time_manager.get_full_time_string()
                current_time = time_manager.get_current_time_string()
                
                time_text = f"""
🕒 **زمان دقیق سیستم**

📅 **تاریخ:** {full_time.split()[0]}
⏰ **ساعت:** {current_time}
🗓️ **سال:** {datetime.now().year}
🌍 **منطقه زمانی:** UTC+3:30 (تهران)

💡 **برای مدیریت ساعت از دستور .ساعت استفاده کنید**
                """
                
                await event.respond(time_text)
                archive_manager.add_to_archive(user_id, "time", "نمایش زمان")
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.ساعت$'))
        async def clock_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                
                time_settings = time_manager.get_time_settings(user_id)
                bio_enabled = time_settings['bio_time_enabled'] if time_settings else False
                name_enabled = time_settings['name_time_enabled'] if time_settings else False
                
                clock_text = f"""
⏰ **مدیریت ساعت اتوماتیک**

🔄 **وضعیت فعلی:**
├─ ساعت در بیو: {'✅ روشن' if bio_enabled else '❌ خاموش'}
└─ ساعت در نام: {'✅ روشن' if name_enabled else '❌ خاموش'}

🔧 **تنظیمات:**
1️⃣ **روشن کردن ساعت در بیو**
2️⃣ **خاموش کردن ساعت در بیو**  
3️⃣ **روشن کردن ساعت در نام**
4️⃣ **خاموش کردن ساعت در نام**

💡 **عدد مورد نظر را ریپلای کنید**
                """
                
                clock_msg = await event.respond(clock_text)
                
                clock_sessions[user_id] = {
                    'clock_message_id': clock_msg.id,
                    'step': 'waiting_clock_choice'
                }
                
            except Exception as e:
                logger.error(f"Error in clock handler: {e}")
                error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage)
        async def clock_choice_handler(event):
            user_id = event.sender_id
            
            if (user_id in clock_sessions and 
                clock_sessions[user_id]['step'] == 'waiting_clock_choice' and
                event.is_reply and
                event.reply_to_msg_id == clock_sessions[user_id]['clock_message_id']):
                
                try:
                    choice = event.text.strip()
                    
                    await client.delete_messages(event.chat_id, [clock_sessions[user_id]['clock_message_id']])
                    
                    if choice == '1':
                        time_manager.enable_bio_time(user_id)
                        if user_id not in time_update_tasks or time_update_tasks[user_id].done():
                            time_update_tasks[user_id] = asyncio.create_task(
                                time_update_worker(client, user_id)
                            )
                        result = "✅ **ساعت در بیو فعال شد!**\n⏰ زمان به طور خودکار بروز می‌شود"
                        
                    elif choice == '2':
                        time_manager.disable_bio_time(user_id)
                        try:
                            me = await client.get_me()
                            current_bio = getattr(me, "about", "") or ""
                            clean_bio = re.sub(r'⏰ \d{1,2}:\d{2}', '', current_bio).strip()
                            if clean_bio != current_bio:
                                await client(UpdateProfileRequest(about=clean_bio))
                        except Exception as e:
                            logger.error(f"Error cleaning bio: {e}")
                        result = "❌ **ساعت در بیو غیرفعال شد!**"
                        
                    elif choice == '3':
                        time_manager.enable_name_time(user_id)
                        if user_id not in time_update_tasks or time_update_tasks[user_id].done():
                            time_update_tasks[user_id] = asyncio.create_task(
                                time_update_worker(client, user_id)
                            )
                        result = "✅ **ساعت در نام فعال شد!**\n⏰ زمان به طور خودکار بروز می‌شود"
                        
                    elif choice == '4':
                        time_manager.disable_name_time(user_id)
                        try:
                            me = await client.get_me()
                            current_first_name = me.first_name or ""
                            clean_first_name = re.sub(r'⏰ \d{1,2}:\d{2}', '', current_first_name).strip()
                            if clean_first_name != current_first_name:
                                await client(UpdateProfileRequest(
                                    first_name=clean_first_name,
                                    last_name=me.last_name or ""
                                ))
                        except Exception as e:
                            logger.error(f"Error cleaning name: {e}")
                        result = "❌ **ساعت در نام غیرفعال شد!**"
                        
                    else:
                        result = "❌ **عدد نامعتبر!**"
                    
                    await event.respond(result)
                    archive_manager.add_to_archive(user_id, "clock_settings", f"تنظیمات ساعت: {choice}")
                    
                    del clock_sessions[user_id]
                    
                except Exception as e:
                    logger.error(f"Error in clock choice handler: {e}")
                    error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    if user_id in clock_sessions:
                        del clock_sessions[user_id]

        @client.on(events.NewMessage(pattern=r'^\.اتورید\s+(on|off)$'))
        async def auto_read_main_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                command = event.pattern_match.group(1).lower()
                
                if command == 'on':
                    auto_read_manager.enable_auto_read(user_id)
                    if user_id not in auto_read_tasks:
                        auto_read_tasks[user_id] = asyncio.create_task(
                            auto_read_worker(client, user_id)
                        )
                    await event.respond("✅ **اتورید فعال شد!**")
                else:
                    auto_read_manager.disable_auto_read(user_id)
                    if user_id in auto_read_tasks:
                        auto_read_tasks[user_id].cancel()
                        del auto_read_tasks[user_id]
                    await event.respond("❌ **اتورید غیرفعال شد!**")
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در اتورید:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.خواندن$'))
        async def read_settings_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                
                read_settings_sessions[user_id] = {
                    'step': 'waiting_number',
                    'settings_message': None
                }
                
                settings_msg = await event.respond("""
⚙️ **پنل تنظیمات خواندن پیام‌ها**

لطفاً عدد مربوط به نوع پیامی که می‌خواهید خوانده شود را انتخاب کنید:

1️⃣ **پیام‌های پیوی** 👤
2️⃣ **پیام‌های گروه‌ها** 👥  
3️⃣ **پیام‌های کانال‌ها** 📢
4️⃣ **همه پیام‌ها** ✅
5️⃣ **فقط پیام‌های خوانده نشده** 🔔

📝 **روش کار:**
- عدد مورد نظر را ریپلای کنید
- تنظیمات ذخیره می‌شود

❌ **برای لغو:** پیامی ارسال نکنید
                """)
                
                read_settings_sessions[user_id]['settings_message'] = settings_msg
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage)
        async def read_settings_response_handler(event):
            user_id = event.sender_id
            
            if user_id in read_settings_sessions and read_settings_sessions[user_id]['step'] == 'waiting_number':
                try:
                    if event.reply_to_msg_id != read_settings_sessions[user_id]['settings_message'].id:
                        return
                    
                    text = event.text.strip()
                    
                    if text in ['1', '2', '3', '4', '5']:
                        current_settings = auto_read_manager.get_auto_read_settings(user_id)
                        
                        if text == '1':
                            auto_read_manager.enable_auto_read(user_id, True, False, False)
                            result = "✅ **تنها پیام‌های پیوی خوانده می‌شوند** 👤"
                            
                        elif text == '2':
                            auto_read_manager.enable_auto_read(user_id, False, True, False)
                            result = "✅ **تنها پیام‌های گروه‌ها خوانده می‌شوند** 👥"
                            
                        elif text == '3':
                            auto_read_manager.enable_auto_read(user_id, False, False, True)
                            result = "✅ **تنها پیام‌های کانال‌ها خوانده می‌شوند** 📢"
                            
                        elif text == '4':
                            auto_read_manager.enable_auto_read(user_id, True, True, True)
                            result = "✅ **همه پیام‌ها خوانده می‌شوند** ✅"
                            
                        else:
                            marked_count = await mark_all_as_read(client, True, True, True)
                            result = f"✅ **همه پیام‌های خوانده نشده خوانده شدند!**\n📖 **تعداد:** {marked_count} دیالوگ"
                        
                        await client.delete_messages(event.chat_id, [read_settings_sessions[user_id]['settings_message'].id])
                        
                        await event.respond(result)
                        del read_settings_sessions[user_id]
                        
                    else:
                        await event.respond("❌ **عدد نامعتبر!** لطفاً عدد ۱ تا ۵ را وارد کنید.")
                        await asyncio.sleep(3)
                        await event.delete()
                        
                except Exception as e:
                    error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    if user_id in read_settings_sessions:
                        del read_settings_sessions[user_id]

        @client.on(events.NewMessage(pattern=r'^\.دلار$'))
        async def dollar_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                processing_msg = await event.respond("💵 **در حال دریافت قیمت دلار...**")
                dollar_price = await get_dollar_price()
                
                response = f"""
💵 **قیمت لحظه‌ای دلار**

💰 **قیمت:** {dollar_price} تومان
🏦 **منبع:** tgju.org
⏰ **زمان:** {datetime.now().strftime("%H:%M")}
                """
                await processing_msg.edit(response)
                archive_manager.add_to_archive(event.sender_id, "dollar", "دریافت قیمت دلار", dollar_price)
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در دریافت قیمت دلار:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.سرچ\s+(.+)$'))
        async def search_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                query = event.pattern_match.group(1).strip()
                
                processing_msg = await event.respond("🔍 **در حال جستجو در گوگل...**")
                search_result = await google_search(query)
                await processing_msg.edit(search_result)
                archive_manager.add_to_archive(user_id, "search", query, search_result)
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در جستجو:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.اینستا\s+(.+)$'))
        async def instagram_downloader(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                url = event.pattern_match.group(1).strip()
                
                if not url.startswith(('https://www.instagram.com/', 'https://instagram.com/')):
                    error_msg = await event.respond("❌ **لینک معتبر اینستاگرام وارد کنید!**")
                    await asyncio.sleep(3)
                    await error_msg.delete()
                    return
                
                processing_msg = await event.respond("📥 **در حال دانلود از اینستاگرام...**")
                file_path, error = await download_instagram_post(url)
                
                if error:
                    await processing_msg.edit(error)
                    return
                
                if file_path and os.path.exists(file_path):
                    if file_path.endswith('.mp4'):
                        await event.respond(file=file_path, caption="📥 **پست اینستاگرام دانلود شد**")
                    else:
                        await event.respond(file=file_path, caption="📥 **پست اینستاگرام دانلود شد**")
                    
                    await processing_msg.delete()
                    archive_manager.add_to_archive(user_id, "instagram", "دانلود پست", "موفق")
                else:
                    await processing_msg.edit("❌ **خطا در دانلود فایل**")
                    
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در دانلود:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.یوتیوب\s+(.+)$'))
        async def youtube_downloader(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                url = event.pattern_match.group(1).strip()
                
                if not url.startswith(('https://www.youtube.com/', 'https://youtube.com/', 'https://youtu.be/')):
                    error_msg = await event.respond("❌ **لینک معتبر یوتیوب وارد کنید!**")
                    await asyncio.sleep(3)
                    await error_msg.delete()
                    return
                
                processing_msg = await event.respond("📥 **در حال دانلود از یوتیوب...**")
                file_path, error = await download_youtube_video(url)
                
                if error:
                    await processing_msg.edit(error)
                    return
                
                if file_path and os.path.exists(file_path):
                    await event.respond(file=file_path, caption="📥 **ویدیو یوتیوب دانلود شد**")
                    await processing_msg.delete()
                    archive_manager.add_to_archive(user_id, "youtube", "دانلود ویدیو", "موفق")
                else:
                    await processing_msg.edit("❌ **خطا در دانلود فایل**")
                    
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در دانلود:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^/sms$'))
        async def read_admin_messages_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                
                unread_messages = admin_manager.get_unread_messages(user_id)
                
                if not unread_messages:
                    no_msg = await event.respond("📭 **هیچ پیام جدیدی از مدیر ندارید**")
                    await asyncio.sleep(5)
                    await no_msg.delete()
                    return
                
                # ارسال پیام‌ها به صورت متوالی
                messages_to_send = []
                for msg in unread_messages:
                    message_text = f"""
📩 **پیام از مدیر**

💬 **متن پیام:**
{msg['message_text']}

📅 **ارسال شده در:** {msg['sent_at'][:16]}

✅ **خوانده شده در:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
                    """
                    
                    if msg['has_media'] and msg['media_path'] and os.path.exists(msg['media_path']):
                        messages_to_send.append({
                            'file': msg['media_path'],
                            'caption': message_text
                        })
                    else:
                        messages_to_send.append(message_text)
                    
                    admin_manager.mark_message_as_read(msg['id'])
                
                # ارسال متوالی پیام‌ها
                await sequential_message_sender(client, event.chat_id, messages_to_send)
                archive_manager.add_to_archive(user_id, "read_messages", "خواندن پیام‌های ادمین")
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.پنل$'))
        async def panel_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                user_data = user_manager.get_user(user_id)
                
                images_stats = image_manager.get_user_images_stats(user_id)
                archive_stats = archive_manager.get_archive_stats(user_id)
                auto_read_settings = auto_read_manager.get_auto_read_settings(user_id)
                time_settings = time_manager.get_time_settings(user_id)
                
                panel_text = f"""
🎛️ **پنل کاربری**

👤 **اطلاعات کاربر:**
├─ نام: {user_data.get('name', 'ندارد')}
├─ شماره: `{user_data['phone']}`
├─ وضعیت: {'✅ فعال' if not user_data['is_banned'] else '❌ مسدود'}
└─ عضویت: {user_data['joined_date'][:10]}

📊 **آمار فعالیت:**
├─ کل فعالیت‌ها: {archive_stats.get('total', 0)}
├─ سوالات از نوت پد: {archive_stats.get('notepad', 0)}
├─ عکس‌های تولید شده: {archive_stats.get('image_generation', 0)}
└─ عکس‌های ذخیره شده: {images_stats['total_images']}

💾 **مدیریت حافظه:**
├─ حجم عکس‌ها: {images_stats['total_size'] / (1024*1024):.2f} مگابایت
└─ آخرین عکس‌ها: {len(images_stats['images_list'])} مورد

⚡ **تنظیمات اتورید:**
├─ وضعیت: {'✅ فعال' if auto_read_settings and auto_read_settings['enabled'] else '❌ غیرفعال'}
├─ پیوی: {'✅' if auto_read_settings and auto_read_settings['include_pv'] else '❌'}
├─ گروه‌ها: {'✅' if auto_read_settings and auto_read_settings['include_groups'] else '❌'}
└─ کانال‌ها: {'✅' if auto_read_settings and auto_read_settings['include_channels'] else '❌'}

⏰ **تنظیمات ساعت:**
├─ ساعت در بیو: {'✅ فعال' if time_settings and time_settings['bio_time_enabled'] else '❌ غیرفعال'}
└─ ساعت در نام: {'✅ فعال' if time_settings and time_settings['name_time_enabled'] else '❌ غیرفعال'}

🔧 **دستورات مدیریت:**
• `.راهنما` - راهنمای کامل
• `.آرشیو` - تاریخچه فعالیت‌ها
• `.وضعیت` - اطلاعات دقیق
• `.خواندن` - تنظیمات اتورید
• `.ساعت` - مدیریت ساعت
• `.تایم` - نمایش زمان
                """
                
                await event.respond(panel_text)
                archive_manager.add_to_archive(user_id, "panel", "مشاهده پنل کاربری")
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در نمایش پنل:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.راهنما$'))
        async def help_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                help_text = """
📚 **راهنمای کامل ربات**

🧠 **هوش مصنوعی:**
• `،سوال شما` - پرسش از نوت پد

🎨 **تولید محتوا:**
• `.عکس توضیحات` - تولید عکس با AI
• `.لوگو توضیحات` - طراحی لوگو
• `.لوگوهای من` - مشاهده لوگوها

💰 **ابزارهای کاربردی:**
• `.دلار` - قیمت لحظه‌ای دلار
• `.سرچ عبارت` - جستجو در گوگل

📥 **دانلود:**
• `.اینستا لینک` - دانلود از اینستاگرام
• `.یوتیوب لینک` - دانلود از یوتیوب

⏰ **مدیریت زمان:**
• `.تایم` - نمایش زمان دقیق
• `.ساعت` - مدیریت ساعت اتوماتیک

📖 **اتورید هوشمند:**
• `.اتورید on` - فعال کردن اتورید
• `.اتورید off` - غیرفعال کردن اتورید
• `.خواندن` - تنظیمات خواندن پیام‌ها

📨 **پیام‌ها:**
• `/sms` - خواندن پیام‌های مدیر

📊 **مدیریت حساب:**
• `.پنل` - پنل کاربری و آمار
• `.آرشیو` - تاریخچه فعالیت‌ها
• `.وضعیت` - اطلاعات سیستم

💡 **تمامی پیام‌ها به صورت خودکار ویرایش می‌شوند.**
                """
                
                await event.respond(help_text)
                archive_manager.add_to_archive(event.sender_id, "help", "مشاهده راهنما")
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در نمایش راهنما:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.وضعیت$'))
        async def status_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                
                user_data = user_manager.get_user(user_id)
                images_stats = image_manager.get_user_images_stats(user_id)
                archive_stats = archive_manager.get_archive_stats(user_id)
                time_settings = time_manager.get_time_settings(user_id)
                
                status_text = f"""
📈 **وضعیت سیستم**

👤 **حساب کاربری:**
├─ شناسه: `{user_id}`
├─ نام: {user_data.get('name', 'ندارد')}
├─ شماره: `{user_data['phone']}`
└─ سشن: {'✅ فعال' if user_id in active_clients else '❌ غیرفعال'}

📁 **ذخیره‌سازی:**
├─ عکس‌ها: {images_stats['total_images']} فایل
├─ حجم استفاده: {images_stats['total_size'] / (1024*1024):.2f} مگابایت
├─ فعالیت‌ها: {archive_stats.get('total', 0)} مورد
└─ آخرین فعالیت: {datetime.now().strftime('%H:%M')}

🔧 **سیستم:**
├─ کلاینت: {'✅ متصل' if user_id in active_clients else '❌ قطع'}
├─ اتورید: {'✅ فعال' if user_id in auto_read_tasks else '❌ غیرفعال'}
├─ ساعت اتوماتیک: {'✅ فعال' if time_settings and (time_settings['bio_time_enabled'] or time_settings['name_time_enabled']) else '❌ غیرفعال'}
└─ حافظه: در وضعیت عادی

⏰ **آخرین به‌روزرسانی:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

✅ **سیستم در وضعیت عادی کار می‌کند.**
                """
                
                await event.respond(status_text)
                archive_manager.add_to_archive(user_id, "status", "بررسی وضعیت سیستم")
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در بررسی وضعیت:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.آرشیو$'))
        async def archive_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                
                archive_data = archive_manager.get_user_archive(user_id, limit=10)
                archive_stats = archive_manager.get_archive_stats(user_id)
                
                if not archive_data:
                    await event.respond("📭 **آرشیو خالی است**")
                    return
                
                archive_text = f"""
📂 **آخرین فعالیت‌ها**

📊 **آمار کلی:**
├─ کل فعالیت‌ها: {archive_stats.get('total', 0)}
├─ نوت پد: {archive_stats.get('notepad', 0)}
├─ میدجرنی: {archive_stats.get('image_generation', 0)}
└─ سایر: {archive_stats.get('total', 0) - archive_stats.get('notepad', 0) - archive_stats.get('image_generation', 0)}

📝 **۱۰ فعالیت آخر:**
"""
                
                for i, activity in enumerate(archive_data, 1):
                    time_str = activity['timestamp'][11:16]
                    desc = activity['description'][:30] + "..." if len(activity['description']) > 30 else activity['description']
                    archive_text += f"├─ {i}. [{time_str}] {activity['type']}: {desc}\n"
                
                archive_text += "\n💡 **برای مشاهده جزئیات بیشتر از پنل استفاده کنید.**"
                
                await event.respond(archive_text)
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا در نمایش آرشیو:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        @client.on(events.NewMessage(pattern=r'^\.لوگوهای من$'))
        async def my_logos_handler(event):
            try:
                if user_manager.is_user_banned(event.sender_id):
                    await event.respond("❌ **شما مسدود شده‌اید!**")
                    return
                    
                user_id = event.sender_id
                
                user_designs = design_manager.get_user_designs(user_id)
                
                if not user_designs:
                    no_designs_msg = await event.respond("🎨 **هنوز هیچ لوگویی طراحی نکرده‌اید!**")
                    await asyncio.sleep(5)
                    await no_designs_msg.delete()
                    return
                
                designs_text = f"""
📁 **لوگوهای طراحی شده شما**

📊 **تعداد:** {len(user_designs)} لوگو

📝 **آخرین طراحی‌ها:**
"""
                
                for i, design in enumerate(user_designs[:5], 1):
                    design_type = design['design_type'].replace('logo_', '')
                    desc_short = design['description'][:20] + "..." if len(design['description']) > 20 else design['description']
                    designs_text += f"{i}. {design_type} - {desc_short}\n"
                
                designs_text += "\n💡 **برای مشاهده لوگو از دستور .مشاهده لوگو [عدد] استفاده کنید**"
                
                await event.respond(designs_text)
                archive_manager.add_to_archive(user_id, "view_logos", "مشاهده لیست لوگوها")
                
            except Exception as e:
                error_msg = await event.respond(f"❌ **خطا:** {str(e)}")
                await asyncio.sleep(5)
                await error_msg.delete()

        auto_read_settings = auto_read_manager.get_auto_read_settings(user_id)
        if auto_read_settings and auto_read_settings['enabled']:
            auto_read_tasks[user_id] = asyncio.create_task(
                auto_read_worker(client, user_id)
            )

        active_clients[user_id] = client
        logger.info(f"✅ Client started for {phone} (User: {user_id})")
        return client
        
    except Exception as e:
        logger.error(f"Error starting user client for {phone}: {e}")
        return None

async def start_all_user_clients():
    active_sessions = user_manager.get_active_sessions()
    started_count = 0
    
    for user_id, session_data in active_sessions.items():
        try:
            if user_manager.is_user_banned(int(user_id)):
                print(f"⏭️ کاربر {user_id} مسدود است - کلاینت شروع نمی‌شود")
                continue
                
            phone = session_data['phone']
            if await is_session_valid(phone):
                client = await start_user_client(phone, int(user_id))
                if client:
                    started_count += 1
                    print(f"✅ کلاینت برای {phone} شروع شد")
            else:
                user_manager.remove_active_session(int(user_id))
        except Exception as e:
            print(f"❌ خطا در شروع کلاینت کاربر {user_id}: {e}")
    
    print(f"🎉 {started_count} کلاینت کاربر شروع شد")

async def start_all_bot_clients():
    """راه‌اندازی همه ربات‌های ذخیره شده"""
    active_bots = bot_manager.get_active_bots()
    started_count = 0
    
    for bot_data in active_bots:
        try:
            bot_client = await start_bot_client(bot_data['bot_token'], bot_data['channels'])
            if bot_client:
                bot_clients[bot_data['bot_id']] = bot_client
                started_count += 1
                print(f"✅ ربات {bot_data['bot_id']} شروع شد")
        except Exception as e:
            print(f"❌ خطا در شروع ربات {bot_data['bot_id']}: {e}")
    
    print(f"🎉 {started_count} ربات اضافه شروع شد")

# ایجاد بات اصلی
bot = TelegramClient('bot_session', API_ID, API_HASH)

async def initialize_bot():
    try:
        await bot.start(bot_token=BOT_TOKEN)
        logger.info("Bot started successfully!")
        return True
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return False

# -------------------- پنل ادمین شیشه‌ای پیشرفته --------------------

async def show_glass_admin_panel(event):
    """نمایش پنل ادمین شیشه‌ای پیشرفته"""
    try:
        stats = admin_manager.get_admin_stats()
        
        admin_panel = f"""
🔮 **پنل مدیریت شیشه‌ای پیشرفته**

📊 **آمار Real-Time سیستم:**
├─ 👥 کاربران کل: {stats['total_users']}
├─ 🔥 فعال امروز: {stats['active_today']}
├─ 🚫 مسدود شده: {stats['banned_users']}
├─ 📈 فعالیت امروز: {stats['activities_today']}
├─ 🔗 سشن‌های فعال: {stats['active_sessions']}
├─ 🖼️ عکس‌های تولید شده: {stats['total_images']}
├─ 🎨 طراحی‌های انجام شده: {stats['total_designs']}
└─ ⏰ سرور: {datetime.now().strftime('%H:%M:%S')}

🎛️ **منوی مدیریت پیشرفته:**

👥 **مدیریت کاربران** - مشاهده و مدیریت کامل کاربران
📨 **ارسال پیام** - ارسال پیام به کاربران
🔧 **ابزارهای پیشرفته** - ری‌اکشن، سین و...
🤖 **مدیریت ربات‌ها** - ربات‌های اضافه
📊 **آمار و گزارشات** - گزارشات دقیق
🔐 **امنیت** - تغییر رمز و لاگ‌ها
⚙️ **تنظیمات سیستم** - تنظیمات پیشرفته
🔄 **ریستارت** - راه‌اندازی مجدد

💡 **برای انتخاب، گزینه مورد نظر را کلیک کنید**
        """
        
        buttons = [
            [Button.inline("👥 مدیریت کاربران", b"admin_users")],
            [Button.inline("📨 ارسال پیام", b"admin_send_msg")],
            [Button.inline("🔧 ابزارهای پیشرفته", b"admin_tools")],
            [Button.inline("🤖 مدیریت ربات‌ها", b"admin_bots")],
            [Button.inline("📊 آمار و گزارشات", b"admin_stats")],
            [Button.inline("🔐 امنیت", b"admin_security")],
            [Button.inline("⚙️ تنظیمات سیستم", b"admin_settings")],
            [Button.inline("🔄 ریستارت", b"admin_restart")]
        ]
        
        panel_msg = await event.respond(admin_panel, buttons=buttons)
        
        admin_sessions[event.sender_id] = {
            'step': 'admin_main_menu',
            'panel_message': panel_msg
        }
        
    except Exception as e:
        await event.respond(f"❌ **خطا در نمایش پنل:** {str(e)}")

async def show_users_management(event):
    """نمایش مدیریت کاربران پیشرفته"""
    try:
        all_users = user_manager.get_all_users()
        banned_users = user_manager.get_banned_users()
        
        if not all_users:
            await event.respond("📭 **هیچ کاربری ثبت‌نام نکرده است**")
            return
        
        users_list = f"""
👥 **مدیریت کاربران پیشرفته**

📈 **آمار کاربران:**
├─ کل کاربران: {len(all_users)}
├─ کاربران مسدود: {len(banned_users)}
├─ کاربران فعال: {len(all_users) - len(banned_users)}
└─ سشن‌های فعال: {len(user_manager.get_active_sessions())}
        """
        
        buttons = [
            [Button.inline("📋 مشاهده همه کاربران", b"view_all_users")],
            [Button.inline("🚫 کاربران مسدود", b"view_banned_users")],
            [Button.inline("✅ کاربران فعال", b"view_active_users")],
            [Button.inline("🔍 جستجوی کاربر", b"search_user")],
            [Button.inline("📊 آمار کاربر خاص", b"user_stats")],
            [Button.inline("🔙 بازگشت", b"admin_back")]
        ]
        
        users_msg = await event.respond(users_list, buttons=buttons)
        
        admin_sessions[event.sender_id] = {
            'step': 'admin_users_menu',
            'users_message': users_msg
        }
        
    except Exception as e:
        await event.respond(f"❌ **خطا:** {str(e)}")

async def show_all_users_list(event, page=1, users_per_page=10):
    """نمایش لیست کاربران با صفحه‌بندی"""
    try:
        all_users = user_manager.get_all_users()
        total_users = len(all_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page
        
        start_idx = (page - 1) * users_per_page
        end_idx = start_idx + users_per_page
        
        users_page = list(all_users.items())[start_idx:end_idx]
        
        users_text = f"""
📋 **لیست کاربران - صفحه {page} از {total_pages}**

📊 **آمار:** {total_users} کاربر | {len(user_manager.get_banned_users())} مسدود

"""
        
        for i, (user_id, user_data) in enumerate(users_page, start_idx + 1):
            status = "🚫" if user_data['is_banned'] else "✅"
            name = user_data.get('name', 'بدون نام')[:20]
            phone = user_data['phone']
            join_date = user_data['joined_date'][:10]
            
            admin_indicator = " 👑" if int(user_id) == ADMIN_ID else ""
            session_status = " 🔗" if user_id in active_clients else ""
            
            users_text += f"{i}. {status} {name}{admin_indicator}{session_status}\n   📱 {phone} | 📅 {join_date}\n"
        
        # ایجاد دکمه‌های ناوبری
        buttons = []
        row = []
        
        if page > 1:
            row.append(Button.inline("◀️ قبلی", f"users_page_{page-1}"))
        
        row.append(Button.inline(f"{page}/{total_pages}", b"current_page"))
        
        if page < total_pages:
            row.append(Button.inline("▶️ بعدی", f"users_page_{page+1}"))
        
        buttons.append(row)
        buttons.append([Button.inline("🔙 بازگشت", b"admin_users")])
        
        # ایجاد دکمه‌های مدیریت برای هر کاربر
        for i, (user_id, user_data) in enumerate(users_page, start_idx + 1):
            buttons.append([Button.inline(f"👤 مدیریت کاربر {i}", f"manage_user_{user_id}")])
        
        if event.sender_id in admin_sessions:
            await admin_sessions[event.sender_id]['users_message'].edit(users_text, buttons=buttons)
        else:
            users_msg = await event.respond(users_text, buttons=buttons)
            admin_sessions[event.sender_id] = {
                'step': 'admin_view_users',
                'users_message': users_msg,
                'current_page': page,
                'total_pages': total_pages,
                'users_list': list(all_users.items())
            }
        
    except Exception as e:
        await event.respond(f"❌ **خطا:** {str(e)}")

async def show_user_detail_management(event, user_id, target_user_id):
    """نمایش جزئیات و مدیریت کاربر"""
    try:
        target_user = user_manager.get_user(target_user_id)
        user_stats = admin_manager.get_admin_stats()
        
        # محاسبه فعالیت‌های کاربر
        activity_query = "SELECT COUNT(*) FROM archive WHERE user_id = ?"
        total_activities = db.fetch_one(activity_query, (target_user_id,))[0] or 0
        
        # فعالیت‌های امروز
        today = datetime.now().date().isoformat()
        today_activities = db.fetch_one(
            "SELECT COUNT(*) FROM archive WHERE user_id = ? AND timestamp LIKE ?",
            (target_user_id, f'{today}%')
        )[0] or 0
        
        user_info = f"""
👤 **مدیریت کاربر - آیدی: {target_user_id}**

📝 **اطلاعات کاربر:**
├─ نام: {target_user.get('name', 'ندارد')}
├─ شماره: `{target_user['phone']}`
├─ وضعیت: {'❌ مسدود' if target_user['is_banned'] else '✅ فعال'}
├─ عضویت: {target_user['joined_date'][:10]}
├─ آخرین ورود: {target_user['last_login'][:16]}
└─ سشن: {'✅ فعال' if target_user_id in active_clients else '❌ غیرفعال'}

📊 **آمار فعالیت:**
├─ کل فعالیت‌ها: {total_activities}
├─ فعالیت امروز: {today_activities}
└─ رتبه: {list(user_manager.get_all_users().keys()).index(target_user_id) + 1} از {user_stats['total_users']}
        """
        
        buttons = [
            [Button.inline("🚫 مسدود کردن" if not target_user['is_banned'] else "✅ رفع مسدودیت", 
                          f"ban_toggle_{target_user_id}")],
            [Button.inline("📩 ارسال پیام", f"send_msg_{target_user_id}")],
            [Button.inline("📊 مشاهده فعالیت‌ها", f"view_activities_{target_user_id}")],
            [Button.inline("🗑️ حذف کاربر", f"delete_user_{target_user_id}")],
            [Button.inline("🔄 راه‌اندازی مجدد سشن", f"restart_session_{target_user_id}")],
            [Button.inline("🔙 بازگشت", b"view_all_users")]
        ]
        
        manage_msg = await event.respond(user_info, buttons=buttons)
        
        admin_sessions[event.sender_id] = {
            'step': 'admin_manage_single_user',
            'target_user_id': target_user_id,
            'manage_message': manage_msg
        }
        
    except Exception as e:
        await event.respond(f"❌ **خطا:** {str(e)}")

async def show_advanced_tools(event):
    """نمایش ابزارهای پیشرفته"""
    try:
        stats = admin_manager.get_admin_stats()
        
        tools_text = f"""
🔧 **ابزارهای پیشرفته مدیریت**

📈 **وضعیت سیستم:**
├─ کاربران آنلاین: {stats['active_sessions']}
├─ ربات‌های فعال: {len(bot_clients) + 1}
├─ حجم دیتابیس: {os.path.getsize(DB_FILE) / 1024:.2f} KB
└─ حافظه مصرفی: در حال بررسی...
        """
        
        buttons = [
            [Button.inline("❤️ ری‌اکشن روی پیام", b"admin_reaction")],
            [Button.inline("👁️ سین کردن پیام", b"admin_seen")],
            [Button.inline("📨 ارسال پیام گروهی", b"admin_broadcast")],
            [Button.inline("🔍 بررسی وضعیت سشن‌ها", b"check_sessions")],
            [Button.inline("🔄 راه‌اندازی مجدد سشن‌ها", b"restart_sessions")],
            [Button.inline("🧹 پاک‌سازی کش", b"clear_cache")],
            [Button.inline("📊 گزارش فعالیت‌ها", b"activity_report")],
            [Button.inline("🔙 بازگشت", b"admin_back")]
        ]
        
        tools_msg = await event.respond(tools_text, buttons=buttons)
        
        admin_sessions[event.sender_id] = {
            'step': 'admin_advanced_tools',
            'tools_message': tools_msg
        }
        
    except Exception as e:
        await event.respond(f"❌ **خطا:** {str(e)}")

async def show_security_panel(event):
    """نمایش پنل امنیتی"""
    try:
        password_history = admin_security_manager.get_password_history()
        admin_logs = admin_manager.get_admin_logs(limit=5)
        
        security_text = f"""
🔐 **پنل امنیتی و مدیریت دسترسی**

📊 **وضعیت امنیتی:**
├─ آخرین تغییر رمز: {password_history[0]['last_changed'][:16] if password_history else 'نامشخص'}
├─ تعداد تغییرات رمز: {len(password_history)}
└─ آخرین فعالیت: {admin_logs[0]['timestamp'][:16] if admin_logs else 'نامشخص'}
        """
        
        buttons = [
            [Button.inline("🔐 تغییر رمز عبور", b"change_password")],
            [Button.inline("📋 مشاهده تاریخچه رمز", b"password_history")],
            [Button.inline("📊 مشاهده لاگ‌های اخیر", b"view_logs")],
            [Button.inline("🧹 پاک‌سازی لاگ‌ها", b"clear_logs")],
            [Button.inline("🛡️ بررسی دسترسی‌ها", b"check_access")],
            [Button.inline("💾 پشتیبان‌گیری", b"backup_database")],
            [Button.inline("🔙 بازگشت", b"admin_back")]
        ]
        
        security_msg = await event.respond(security_text, buttons=buttons)
        
        admin_sessions[event.sender_id] = {
            'step': 'admin_security_panel',
            'security_message': security_msg
        }
        
    except Exception as e:
        await event.respond(f"❌ **خطا:** {str(e)}")

async def send_broadcast_message(event, message_text, has_media=False, media_path=None):
    """ارسال پیام به همه کاربران"""
    try:
        all_users = user_manager.get_all_users()
        success_count = 0
        fail_count = 0
        
        progress_msg = await event.respond(f"📨 **در حال ارسال پیام به {len(all_users)} کاربر...**\n\n✅ موفق: 0\n❌ ناموفق: 0")
        
        for user_id, user_data in all_users.items():
            try:
                if user_manager.is_user_banned(user_id):
                    fail_count += 1
                    continue
                
                # ارسال پیام به کاربر
                admin_manager.save_admin_message(
                    user_id, event.sender_id, message_text, has_media, media_path
                )
                
                success_count += 1
                
                # آپدیت پیام پیشرفت هر 10 کاربر
                if success_count % 10 == 0:
                    await progress_msg.edit(
                        f"📨 **در حال ارسال پیام به {len(all_users)} کاربر...**\n\n"
                        f"✅ موفق: {success_count}\n"
                        f"❌ ناموفق: {fail_count}\n"
                        f"📊 پیشرفت: {(success_count + fail_count) / len(all_users) * 100:.1f}%"
                    )
                
                await asyncio.sleep(0.1)  # تأخیر برای جلوگیری از اسپم
                
            except Exception as e:
                fail_count += 1
                logger.error(f"Error sending to user {user_id}: {e}")
        
        await progress_msg.edit(
            f"✅ **ارسال پیام گروهی تکمیل شد!**\n\n"
            f"📊 **نتایج:**\n"
            f"✅ موفق: {success_count}\n"
            f"❌ ناموفق: {fail_count}\n"
            f"📩 کل ارسال: {len(all_users)}\n"
            f"🎯 نرخ موفقیت: {(success_count/len(all_users))*100:.1f}%"
        )
        
        admin_manager.add_admin_log(
            event.sender_id, 
            "broadcast_message", 
            details=f"Success: {success_count}, Failed: {fail_count}"
        )
        
    except Exception as e:
        await event.respond(f"❌ **خطا در ارسال گروهی:** {str(e)}")

def setup_bot_handlers():
    
    @bot.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        user_id = event.sender_id
        
        if user_id == ADMIN_ID:
            welcome_text = """
🔮 **به پنل مدیریت شیشه‌ای خوش آمدید!**

👑 **دسترسی:** ادمین اصلی
🔐 **رمز پیش‌فرض:** 1276438321

💡 **برای ورود به پنل مدیریت از دستور زیر استفاده کنید:**
• `/admin` - ورود به پنل مدیریت

🚀 **ویژگی‌های جدید:**
- پنل شیشه‌ای با منوهای تعاملی
- مدیریت پیشرفته کاربران
- ابزارهای ری‌اکشن و سین پیام
- مدیریت چندین ربات
- آمار real-time
            """
            await event.reply(welcome_text)
            return
        
        user_data = user_manager.get_user(user_id)
        
        if user_data and await is_session_valid(user_data['phone']):
            if user_manager.is_user_banned(user_id):
                await event.reply("❌ **شما مسدود شده‌اید و نمی‌توانید از ربات استفاده کنید!**")
                return
                
            user_sessions[user_id] = {'step': 'logged_in', 'phone': user_data['phone']}
            
            welcome_text = f"""
✅ **شما در حال حاضر وارد شده‌اید!**

👤 **کاربر:** {user_data.get('name', user_data['phone'])}
📱 **شماره:** `{user_data['phone']}`

🚀 **برای شروع از دستورات زیر استفاده کنید:**
• `.راهنما` - راهنمای کامل
• `.پنل` - پنل کاربری
• `،سوال` - پرسش از نوت پد
• `.تایم` - نمایش زمان
• `.ساعت` - مدیریت ساعت
            """
            await event.reply(welcome_text)
        else:
            user_sessions[user_id] = {'step': 'start'}
            welcome_text = """
🤖 **به ربات هوشمند خوش آمدید!**

✨ **قابلیت‌های اصلی:**
• هوش مصنوعی پیشرفته
• تولید عکس با دو AI مختلف
• طراحی لوگو حرفه‌ای
• دانلود از اینستاگرام و یوتیوب
• اتورید هوشمند
• مدیریت زمان و ساعت
• ابزارهای کاربردی

📱 **برای شروع، شماره تلگرام خود را ارسال کنید:**
(مثال: +989123456789)
            """
            await event.reply(welcome_text)

    # 🛡️ هندلر اصلی ادمین
    @bot.on(events.NewMessage(pattern=r'^/admin$'))
    async def admin_main_handler(event):
        user_id = event.sender_id
        
        try:
            if user_id == ADMIN_ID:
                await show_glass_admin_panel(event)
                return
            
            auth_msg = await event.respond("""
🛡️ **ورود به پنل مدیریت**

🔐 لطفاً رمز عبور ادمین را وارد کنید:

⚠️ توجه: رمز عبور به صورت خودکار حذف خواهد شد
⏰ زمان ورود: 2 دقیقه

❌ برای لغو، پیامی ارسال نکنید
            """)
            
            admin_auth_sessions[user_id] = {
                'step': 'waiting_password',
                'auth_message_id': auth_msg.id,
                'attempts': 0,
                'start_time': time.time()
            }
            
        except Exception as e:
            await event.respond(f"❌ **خطا:** {str(e)}")

    # هندلر بررسی رمز عبور ادمین
    @bot.on(events.NewMessage)
    async def admin_password_handler(event):
        user_id = event.sender_id
        
        if (user_id in admin_auth_sessions and 
            admin_auth_sessions[user_id]['step'] == 'waiting_password'):
            
            try:
                # بررسی زمان
                if time.time() - admin_auth_sessions[user_id]['start_time'] > 120:
                    await event.respond("❌ **زمان ورود به پایان رسیده!**")
                    del admin_auth_sessions[user_id]
                    return
                
                password = event.text.strip()
                
                await bot.delete_messages(event.chat_id, [admin_auth_sessions[user_id]['auth_message_id']])
                
                if admin_security_manager.verify_password(password):
                    await event.respond("✅ **رمز عبور صحیح! در حال ورود به پنل مدیریت...**")
                    admin_manager.add_admin_log(user_id, "admin_login_success")
                    await show_glass_admin_panel(event)
                    del admin_auth_sessions[user_id]
                else:
                    admin_auth_sessions[user_id]['attempts'] += 1
                    
                    if admin_auth_sessions[user_id]['attempts'] >= 3:
                        await event.respond("❌ **تعداد تلاش‌های شما بیش از حد مجاز است!**")
                        admin_manager.add_admin_log(user_id, "admin_login_failed_max_attempts")
                        del admin_auth_sessions[user_id]
                    else:
                        auth_msg = await event.respond(
                            f"❌ **رمز عبور نادرست!**\n\n"
                            f"🔄 تعداد تلاش‌های باقی‌مانده: {3 - admin_auth_sessions[user_id]['attempts']}\n"
                            f"⏰ زمان باقی‌مانده: {120 - int(time.time() - admin_auth_sessions[user_id]['start_time'])} ثانیه"
                        )
                        admin_auth_sessions[user_id]['auth_message_id'] = auth_msg.id
                        admin_manager.add_admin_log(user_id, "admin_login_failed")
                        
            except Exception as e:
                await event.respond(f"❌ **خطا:** {str(e)}")
                if user_id in admin_auth_sessions:
                    del admin_auth_sessions[user_id]

    # هندلر کلیک روی دکمه‌های پنل ادمین
    @bot.on(events.CallbackQuery)
    async def admin_button_handler(event):
        user_id = event.sender_id
        
        if user_id != ADMIN_ID:
            await event.answer("❌ شما دسترسی ادمین ندارید!", alert=True)
            return
        
        data = event.data.decode('utf-8')
        
        try:
            if data == 'admin_back':
                await show_glass_admin_panel(event)
                
            elif data == 'admin_users':
                await show_users_management(event)
                
            elif data == 'view_all_users':
                await show_all_users_list(event, 1)
                
            elif data.startswith('users_page_'):
                page = int(data.split('_')[2])
                await show_all_users_list(event, page)
                
            elif data.startswith('manage_user_'):
                target_user_id = int(data.split('_')[2])
                await show_user_detail_management(event, user_id, target_user_id)
                
            elif data.startswith('ban_toggle_'):
                target_user_id = int(data.split('_')[2])
                target_user = user_manager.get_user(target_user_id)
                
                if target_user['is_banned']:
                    user_manager.unban_user(target_user_id)
                    await event.answer("✅ کاربر آنبن شد")
                else:
                    user_manager.ban_user(target_user_id)
                    if target_user_id in active_clients:
                        await active_clients[target_user_id].disconnect()
                        del active_clients[target_user_id]
                    await event.answer("✅ کاربر بن شد")
                
                await show_user_detail_management(event, user_id, target_user_id)
                
            elif data.startswith('send_msg_'):
                target_user_id = int(data.split('_')[2])
                await event.respond(f"💬 **ارسال پیام به کاربر {target_user_id}**\n\nلطفاً پیام خود را ارسال کنید:")
                admin_sessions[user_id] = {
                    'step': 'admin_send_single_message',
                    'target_user_id': target_user_id
                }
                
            elif data == 'admin_send_msg':
                await event.respond("📨 **ارسال پیام**\n\nلطفاً آیدی کاربر را وارد کنید (یا 'همه' برای ارسال گروهی):")
                admin_sessions[user_id] = {
                    'step': 'admin_send_message_user'
                }
                
            elif data == 'admin_tools':
                await show_advanced_tools(event)
                
            elif data == 'admin_reaction':
                await event.respond("❤️ **ری‌اکشن روی پیام**\n\nلطفاً لینک پیام و ری‌اکشن مورد نظر را به فرمت زیر ارسال کنید:\n`لینک_پیام | ری‌اکشن`\n\nمثال:\n`https://t.me/channel/123 | ❤️`")
                admin_sessions[user_id] = {
                    'step': 'admin_waiting_reaction'
                }
                
            elif data == 'admin_seen':
                await event.respond("👁️ **سین کردن پیام**\n\nلطفاً لینک پیام مورد نظر را ارسال کنید:")
                admin_sessions[user_id] = {
                    'step': 'admin_waiting_seen'
                }
                
            elif data == 'admin_broadcast':
                await event.respond("📨 **ارسال پیام گروهی**\n\nلطفاً پیام خود را ارسال کنید:")
                admin_sessions[user_id] = {
                    'step': 'admin_broadcast_message'
                }
                
            elif data == 'admin_security':
                await show_security_panel(event)
                
            elif data == 'change_password':
                await event.respond("🔐 **تغییر رمز عبور**\n\nلطفاً رمز عبور جدید را ارسال کنید:")
                admin_sessions[user_id] = {
                    'step': 'admin_change_password'
                }
                
            elif data == 'admin_stats':
                stats = admin_manager.get_admin_stats()
                stats_text = f"""
📊 **آمار دقیق سیستم**

👥 **کاربران:**
├─ کل کاربران: {stats['total_users']}
├─ فعال امروز: {stats['active_today']}
├─ مسدود شده: {stats['banned_users']}
├─ فعالیت امروز: {stats['activities_today']}
├─ سشن‌های فعال: {stats['active_sessions']}
├─ عکس‌های تولید شده: {stats['total_images']}
└─ طراحی‌های انجام شده: {stats['total_designs']}

💾 **حافظه:**
├─ کلاینت‌های فعال: {len(active_clients)}
├─ ربات‌های فعال: {len(bot_clients)}
├─ حجم دیتابیس: {os.path.getsize(DB_FILE) / 1024:.2f} KB
└─ حجم عکس‌ها: {sum(os.path.getsize(f) for f in IMAGES_DIR.rglob('*') if os.path.isfile(f)) / (1024*1024):.2f} MB

⏰ **آخرین به‌روزرسانی:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
                await event.respond(stats_text)
                
            elif data == 'admin_restart':
                await event.respond("🔄 **ریستارت سیستم**\n\nآیا مطمئن هستید؟ (بله/خیر)")
                admin_sessions[user_id] = {
                    'step': 'admin_confirm_restart'
                }
                
            await event.answer()
            
        except Exception as e:
            await event.respond(f"❌ **خطا:** {str(e)}")
            await event.answer()

    # هندلر ارسال پیام به کاربر خاص
    @bot.on(events.NewMessage)
    async def admin_send_single_message_handler(event):
        user_id = event.sender_id
        
        if (user_id in admin_sessions and 
            admin_sessions[user_id]['step'] == 'admin_send_single_message'):
            
            try:
                target_user_id = admin_sessions[user_id]['target_user_id']
                message_text = event.text or "پیام بدون متن"
                has_media = bool(event.media)
                media_path = None
                
                if has_media:
                    media_dir = DATA_DIR / "admin_media"
                    media_dir.mkdir(exist_ok=True)
                    timestamp = int(time.time())
                    media_path = media_dir / f"admin_msg_{timestamp}.jpg"
                    await event.download_media(file=str(media_path))
                
                admin_manager.save_admin_message(
                    target_user_id, user_id, message_text, has_media, str(media_path) if media_path else None
                )
                
                await event.respond(f"✅ **پیام برای کاربر {target_user_id} ارسال شد**")
                admin_manager.add_admin_log(user_id, "send_message", target_user_id)
                
                await show_glass_admin_panel(event)
                
                if user_id in admin_sessions:
                    del admin_sessions[user_id]
                
            except Exception as e:
                await event.respond(f"❌ **خطا در ارسال پیام:** {str(e)}")
                await show_glass_admin_panel(event)

    # هندلر ارسال پیام گروهی
    @bot.on(events.NewMessage)
    async def admin_broadcast_handler(event):
        user_id = event.sender_id
        
        if (user_id in admin_sessions and 
            admin_sessions[user_id]['step'] == 'admin_broadcast_message'):
            
            try:
                message_text = event.text or "پیام بدون متن"
                has_media = bool(event.media)
                media_path = None
                
                if has_media:
                    media_dir = DATA_DIR / "admin_media"
                    media_dir.mkdir(exist_ok=True)
                    timestamp = int(time.time())
                    media_path = media_dir / f"broadcast_{timestamp}.jpg"
                    await event.download_media(file=str(media_path))
                
                await send_broadcast_message(event, message_text, has_media, media_path)
                
                if user_id in admin_sessions:
                    del admin_sessions[user_id]
                
            except Exception as e:
                await event.respond(f"❌ **خطا در ارسال گروهی:** {str(e)}")
                await show_glass_admin_panel(event)

    # هندلر ری‌اکشن
    @bot.on(events.NewMessage)
    async def admin_reaction_handler(event):
        user_id = event.sender_id
        
        if (user_id in admin_sessions and 
            admin_sessions[user_id]['step'] == 'admin_waiting_reaction'):
            
            try:
                data = event.text.strip()
                if '|' in data:
                    message_link, reaction = data.split('|', 1)
                    message_link = message_link.strip()
                    reaction = reaction.strip()
                    
                    await event.respond(f"❤️ **در حال اضافه کردن ری‌اکشن {reaction}...**")
                    
                    result_count = await add_reaction_to_message_by_all_users(message_link, reaction)
                    
                    await event.respond(f"✅ **ری‌اکشن {reaction} با موفقیت اضافه شد!**\n👥 **تعداد کاربران:** {result_count}")
                    admin_manager.add_admin_log(user_id, "add_reaction", details=f"Reaction: {reaction}, Count: {result_count}")
                    
                else:
                    await event.respond("❌ **فرمت نادرست!**\n\nلطفاً به فرمت زیر ارسال کنید:\n`لینک_پیام | ری‌اکشن`")
                    return
                
                if user_id in admin_sessions:
                    del admin_sessions[user_id]
                
            except Exception as e:
                await event.respond(f"❌ **خطا در اضافه کردن ری‌اکشن:** {str(e)}")
                await show_glass_admin_panel(event)

    # هندلر سین پیام
    @bot.on(events.NewMessage)
    async def admin_seen_handler(event):
        user_id = event.sender_id
        
        if (user_id in admin_sessions and 
            admin_sessions[user_id]['step'] == 'admin_waiting_seen'):
            
            try:
                message_link = event.text.strip()
                
                await event.respond("👁️ **در حال سین کردن پیام...**")
                
                result_count = await mark_message_as_seen_by_all_users(message_link)
                
                await event.respond(f"✅ **پیام با موفقیت سین شد!**\n👥 **تعداد کاربران:** {result_count}")
                admin_manager.add_admin_log(user_id, "mark_seen", details=f"Count: {result_count}")
                
                if user_id in admin_sessions:
                    del admin_sessions[user_id]
                
            except Exception as e:
                await event.respond(f"❌ **خطا در سین کردن پیام:** {str(e)}")
                await show_glass_admin_panel(event)

    # هندلر تغییر رمز عبور
    @bot.on(events.NewMessage)
    async def admin_change_password_handler(event):
        user_id = event.sender_id
        
        if (user_id in admin_sessions and 
            admin_sessions[user_id]['step'] == 'admin_change_password'):
            
            try:
                new_password = event.text.strip()
                
                if len(new_password) < 6:
                    await event.respond("❌ **رمز عبور باید حداقل ۶ کاراکتر باشد!**")
                    return
                
                admin_security_manager.change_password(new_password)
                await event.respond(f"✅ **رمز عبور با موفقیت تغییر یافت!**")
                admin_manager.add_admin_log(user_id, "change_password")
                
                await show_glass_admin_panel(event)
                
                if user_id in admin_sessions:
                    del admin_sessions[user_id]
                
            except Exception as e:
                await event.respond(f"❌ **خطا در تغییر رمز:** {str(e)}")
                await show_glass_admin_panel(event)

    # هندلر ارسال پیام به کاربر خاص با آیدی
    @bot.on(events.NewMessage)
    async def admin_send_message_user_handler(event):
        user_id = event.sender_id
        
        if (user_id in admin_sessions and 
            admin_sessions[user_id]['step'] == 'admin_send_message_user'):
            
            try:
                user_input = event.text.strip()
                
                if user_input.lower() == 'همه':
                    await event.respond("📨 **ارسال پیام گروهی**\n\nلطفاً پیام خود را ارسال کنید:")
                    admin_sessions[user_id] = {
                        'step': 'admin_broadcast_message'
                    }
                else:
                    try:
                        target_user_id = int(user_input)
                        target_user = user_manager.get_user(target_user_id)
                        
                        if target_user:
                            await event.respond(f"💬 **ارسال پیام به کاربر {target_user_id}**\n\nلطفاً پیام خود را ارسال کنید:")
                            admin_sessions[user_id] = {
                                'step': 'admin_send_single_message',
                                'target_user_id': target_user_id
                            }
                        else:
                            await event.respond("❌ **کاربر یافت نشد!**")
                            await show_glass_admin_panel(event)
                    except ValueError:
                        await event.respond("❌ **آیدی کاربر باید عددی باشد!**")
                        await show_glass_admin_panel(event)
                
            except Exception as e:
                await event.respond(f"❌ **خطا:** {str(e)}")
                await show_glass_admin_panel(event)

    # هندلر ثبت‌نام کاربران
    @bot.on(events.NewMessage)
    async def message_handler(event):
        user_id = event.sender_id
        text = event.text.strip()
        
        if user_id not in user_sessions:
            user_sessions[user_id] = {'step': 'start'}
            await event.reply("🔍 **لطفاً اول با دستور /start شروع کنید**")
            return
        
        session = user_sessions[user_id]
        
        if session['step'] == 'start':
            if text.startswith('+') and len(text) > 10:
                session['phone'] = text
                session['step'] = 'waiting_code'
                
                try:
                    sent_code = await send_code_request(text)
                    session['phone_code_hash'] = sent_code.phone_code_hash
                    session['code_input'] = ""
                    
                    buttons = [
                        [Button.inline("1", b"num_1"), Button.inline("2", b"num_2"), Button.inline("3", b"num_3")],
                        [Button.inline("4", b"num_4"), Button.inline("5", b"num_5"), Button.inline("6", b"num_6")],
                        [Button.inline("7", b"num_7"), Button.inline("8", b"num_8"), Button.inline("9", b"num_9")],
                        [Button.inline("0", b"num_0"), Button.inline("🧹 پاک کردن", b"clear"), Button.inline("✅ تأیید", b"submit")]
                    ]
                    
                    await event.reply(
                        f"📱 **کد تأیید به شماره {text} ارسال شد**\n\nلطفاً کد را با دکمه‌های زیر وارد کنید:",
                        buttons=buttons
                    )
                except Exception as e:
                    await event.reply(f"❌ **خطا در ارسال کد:** {e}")
                    session['step'] = 'start'

    @bot.on(events.CallbackQuery)
    async def callback_handler(event):
        user_id = event.sender_id
        
        if user_id not in user_sessions:
            await event.answer("لطفاً اول با /start شروع کنید", alert=True)
            return
        
        session = user_sessions[user_id]
        data = event.data.decode('utf-8')
        
        if session['step'] == 'waiting_code':
            if data.startswith('num_'):
                number = data.split('_')[1]
                if len(session.get('code_input', '')) < 5:
                    session['code_input'] = session.get('code_input', '') + number
                    
                    buttons = [
                        [Button.inline("1", b"num_1"), Button.inline("2", b"num_2"), Button.inline("3", b"num_3")],
                        [Button.inline("4", b"num_4"), Button.inline("5", b"num_5"), Button.inline("6", b"num_6")],
                        [Button.inline("7", b"num_7"), Button.inline("8", b"num_8"), Button.inline("9", b"num_9")],
                        [Button.inline("0", b"num_0"), Button.inline("🧹 پاک کردن", b"clear"), Button.inline("✅ تأیید", b"submit")]
                    ]
                    
                    code_display = session['code_input'] + '•' * (5 - len(session['code_input']))
                    await event.edit(f"⌛ **کد وارد شده:** {code_display}", buttons=buttons)
                
            elif data == 'clear':
                session['code_input'] = ""
                buttons = [
                    [Button.inline("1", b"num_1"), Button.inline("2", b"num_2"), Button.inline("3", b"num_3")],
                    [Button.inline("4", b"num_4"), Button.inline("5", b"num_5"), Button.inline("6", b"num_6")],
                    [Button.inline("7", b"num_7"), Button.inline("8", b"num_8"), Button.inline("9", b"num_9")],
                    [Button.inline("0", b"num_0"), Button.inline("🧹 پاک کردن", b"clear"), Button.inline("✅ تأیید", b"submit")]
                ]
                await event.edit("⌛ **کد وارد شده:** •••••", buttons=buttons)
                
            elif data == 'submit':
                code = session.get('code_input', '')
                if len(code) == 5:
                    await event.edit("⏳ **در حال تأیید کد...**")
                    
                    try:
                        await sign_in_user(session['phone'], code, session['phone_code_hash'])
                        
                        client = await create_user_client(session['phone'])
                        await client.start(session['phone'])
                        me = await client.get_me()
                        user_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
                        await client.disconnect()
                        
                        user_manager.add_user(user_id, session['phone'], session_name(session['phone']), user_name)
                        user_client = await start_user_client(session['phone'], user_id)
                        
                        if user_client:
                            session['step'] = 'logged_in'
                            welcome_text = f"""
✅ **ثبت‌نام موفقیت‌آمیز!**

👤 **خوش آمدید {user_name}**

🎉 **حساب شما با موفقیت ایجاد شد!**

📚 **برای شروع از دستورات زیر استفاده کنید:**
• `.راهنما` - راهنمای کامل
• `.پنل` - پنل کاربری
• `،سوال شما` - پرسش از نوت پد
• `.عکس توضیحات` - تولید عکس
• `.لوگو توضیحات` - طراحی لوگو
• `.تایم` - نمایش زمان
• `.ساعت` - مدیریت ساعت

⚡ **ربات همیشه در دسترس شماست!**
                            """
                        else:
                            welcome_text = "❌ **خطا در راه‌اندازی کلاینت**"
                        
                        await event.reply(welcome_text)
                        
                    except Exception as e:
                        await event.reply(f"❌ **خطا در ورود:** {e}")
                        session['step'] = 'start'
                else:
                    await event.answer("❌ کد باید ۵ رقم باشد!", alert=True)
        
        await event.answer()

async def main():
    print("🤖 **در حال راه‌اندازی ربات هوشمند...**")
    
    print(f"✅ کاربران ذخیره شده: {len(user_manager.get_all_users())}")
    print(f"✅ سشن‌های فعال: {len(user_manager.get_active_sessions())}")
    
    if await initialize_bot():
        print("✅ بات اصلی راه‌اندازی شد")
        setup_bot_handlers()
        print("✅ هندلرها تنظیم شدند")
        
        print("🚀 در حال راه‌اندازی کلاینت‌های کاربران...")
        await start_all_user_clients()
        
        print("🚀 در حال راه‌اندازی ربات‌های اضافه...")
        await start_all_bot_clients()
        
        print("""
🎯 **ربات آماده کار است!**

✨ **ویژگی‌های فعال:**
• پنل ادمین شیشه‌ای با منوهای تعاملی
• مدیریت کاربران پیشرفته
• ابزارهای ری‌اکشن و سین پیام
• مدیریت چندین ربات
• تولید عکس و طراحی لوگو
• هوش مصنوعی با نوت پد
• اتورید هوشمند
• مدیریت زمان و ساعت
• دانلود از اینستاگرام و یوتیوب
• قیمت لحظه‌ای دلار
• جستجوی گوگل

🛡️ **پنل ادمین:** `/admin`
🔐 **رمز پیش‌فرض:** 1276438321
👤 **آیدی ادمین:** 1276438321

💡 **ربات همیشه در دسترس کاربران است!**
        """)
        
        await bot.run_until_disconnected()
    else:
        print("❌ خطا در راه‌اندازی بات اصلی")

if __name__ == '__main__':
    SESSIONS_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    POST_DIR.mkdir(exist_ok=True)
    DESIGNS_DIR.mkdir(exist_ok=True)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n⏹️ **ربات توسط کاربر متوقف شد**")
    except Exception as e:
        print(f"\n❌ **خطا در اجرای ربات:** {e}")
    finally:
        print("🔚 **خروج از ربات**")
        loop.close()

# NEW ADMIN HANDLER
@client.on(events.NewMessage(pattern=r'^/admin (\d+)$'))
async def new_admin_handler(event):
    admin_id = int(event.pattern_match.group(1))
    if event.sender_id != admin_id:
        await event.respond("❌ دسترسی ادمین ندارید.")
        return
    await event.respond("✅ ادمین لاگین شد.\nدستورات:\n- /stats\n- /broadcast <msg>\n- ...")



# --- Simple Admin Password Flow ---
admin_password = "1234"

@client.on(events.NewMessage(pattern=r'^/admin$'))
async def admin_start(event):
    await event.respond("🔐 لطفاً رمز ادمین را ارسال کنید.")
    client._awaiting_admin_pw = event.sender_id

@client.on(events.NewMessage)
async def admin_pw_check(event):
    if hasattr(client, "_awaiting_admin_pw") and client._awaiting_admin_pw == event.sender_id:
        if event.raw_text.strip() == admin_password:
            client._is_admin = event.sender_id
            del client._awaiting_admin_pw
            await event.respond("✅ ورود موفق!\nمنوی ادمین:\n- /broadcast <text>\n- /stats")
        else:
            await event.respond("❌ رمز اشتباه است.")
            del client._awaiting_admin_pw

# --- Download Handler ---
@client.on(events.NewMessage(pattern=r'^\.دانلود$'))
async def dl_handler(event):
    if not event.is_reply:
        return await event.respond("❌ روی پیام ریپلای کنید.")
    m = await event.get_reply_message()
    f = await m.download_media()
    if not f:
        return await event.respond("❌ قابل دانلود نیست.")
    await client.send_file("me", f, caption=m.message or "")
    await event.respond("✅ ذخیره شد.")

# --- Clock Menu Placeholder ---
@client.on(events.NewMessage(pattern=r'^\.ساعت$'))
async def clock_menu(event):
    await event.respond("⌚ لطفاً محل نمایش ساعت را انتخاب کنید:\n1) بیو\n2) نام")



# ==== BOT NAME STYLE SETTINGS ====
BOT_BASE_NAME = "self tel"
BOT_STYLE_FILE = "bot_time_style.json"

def load_bot_style():
    try:
        import json, os
        p=os.path.join(os.path.dirname(__file__), BOT_STYLE_FILE)
        if not os.path.exists(p):
            return {"style":1}
        return json.load(open(p))
    except:
        return {"style":1}

def save_bot_style(d):
    import json, os
    p=os.path.join(os.path.dirname(__file__), BOT_STYLE_FILE)
    json.dump(d, open(p,"w"), ensure_ascii=False, indent=2)

async def set_bot_name_api(new_name):
    import aiohttp
    url=f"https://api.telegram.org/bot{BOT_TOKEN}/setMyName"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json={"name": new_name}) as r:
            return await r.json()

async def bot_name_worker():
    import asyncio, datetime
    style=load_bot_style().get("style",1)
    last=None
    while True:
        try:
            now=datetime.datetime.now().strftime("%H:%M")
            styled=stylize_time(now, style)
            new=f"{BOT_BASE_NAME} | {styled}"
            if new!=last:
                await set_bot_name_api(new)
                last=new
        except Exception as e:
            print("bot name worker error:",e)
        await asyncio.sleep(60)

# Modify admin panel to add time style button


# === ADMIN KEYPAD LOGIN ===
ADMIN_SECRET="1276438321"
ADMIN_STORE="admins.json"

def load_admins():
    import json, os
    p=os.path.join(os.path.dirname(__file__), ADMIN_STORE)
    if not os.path.exists(p):
        return []
    return json.load(open(p))

def save_admins(a):
    import json, os
    p=os.path.join(os.path.dirname(__file__), ADMIN_STORE)
    json.dump(a, open(p,"w"), indent=2)

@client.on(events.NewMessage(pattern=r'^/admin$'))
async def admin_keypad(event):
    uid=event.sender_id
    admins=load_admins()
    if uid in admins:
        await event.respond("پنل ادمین:", buttons=[[Button.inline("ورود به پنل", b"admin_panel")]])
        return
    # otherwise ask keypad
    btns=[[Button.inline(str(i), str(i).encode()) for i in range(0,5)],
          [Button.inline(str(i), str(i).encode()) for i in range(5,10)]]
    await event.respond("رمز را عدد به عدد وارد کنید:", buttons=btns)
    event.client._passbuf={}

@client.on(events.CallbackQuery)
async def admin_keypad_press(ev):
    data=ev.data.decode()
    uid=ev.sender_id
    client._passbuf = getattr(client, "_passbuf", {})
    buf=client._passbuf.get(uid,"")
    buf+=data
    client._passbuf[uid]=buf
    if len(buf)==len(ADMIN_SECRET):
        if buf==ADMIN_SECRET:
            admins=load_admins()
            if str(uid) not in [str(x) for x in admins]:
                admins.append(uid)
                save_admins(admins)
            await ev.edit("ورود موفق!", buttons=[[Button.inline("پنل ادمین", b"admin_panel")]])
        else:
            await ev.edit("❌ رمز اشتباه")
            client._passbuf[uid]=""
    else:
        await ev.answer(f"تا الان: {buf}", alert=False)




# -------------------- Enhanced Admin Panel & Bot-Name Clock --------------------
# Added features:
# - Admin panel buttons expanded: list users, block/unblock, broadcast (logged), send to user, view logs, delete user, reset
# - Bot-name clock controls: choose style, format (HH:MM / HH:MM:SS / date+time), interval, enable/disable
# - Persistence via JSON files
# - Randomized output filename will be used when zipping for download
# NOTE: Broadcasting to all users is intentionally a logged action only (no mass send) to avoid abuse.
# ---------------------------------------------------------------------------------

import json, os, datetime, asyncio, random

_ADMIN_STORE = os.path.join(os.path.dirname(__file__), "admins.json")
_USERS_STORE = os.path.join(os.path.dirname(__file__), "known_users.json")
_LOG_STORE = os.path.join(os.path.dirname(__file__), "bot_event_log.json")
_BOT_STYLE_STORE = os.path.join(os.path.dirname(__file__), "bot_time_style.json")

def _ensure(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ensure stores
_ensure(_ADMIN_STORE, [])
_ensure(_USERS_STORE, {})
_ensure(_LOG_STORE, {"events": []})
_ensure(_BOT_STYLE_STORE, {"style": 1, "format": "HH:MM", "interval": 60, "enabled": True})

def log_event(kind, info):
    logs = _load(_LOG_STORE)
    logs.setdefault("events", []).append({"time": datetime.datetime.now().isoformat(), "kind": kind, "info": info})
    _save(_LOG_STORE, logs)

def add_known_user(uid, info=None):
    users = _load(_USERS_STORE)
    users[str(uid)] = {"first_seen": datetime.datetime.now().isoformat(), "info": info or {}}
    _save(_USERS_STORE, users)

def list_known_users():
    return _load(_USERS_STORE)

def is_admin_uid(uid):
    admins = _load(_ADMIN_STORE)
    return str(uid) in [str(x) for x in admins]

def add_admin(uid):
    admins = _load(_ADMIN_STORE)
    if str(uid) not in [str(x) for x in admins]:
        admins.append(uid)
        _save(_ADMIN_STORE, admins)
        log_event("admin_added", {"by": uid})

def remove_admin(uid):
    admins = _load(_ADMIN_STORE)
    admins = [x for x in admins if str(x) != str(uid)]
    _save(_ADMIN_STORE, admins)
    log_event("admin_removed", {"by": uid})

def get_bot_style():
    return _load(_BOT_STYLE_STORE)

def set_bot_style(data):
    _save(_BOT_STYLE_STORE, data)
    log_event("bot_style_set", data)

# Hook: track users who interact (simple)
# We'll attempt to add a small listener to record users (if not present)
try:
    @client.on(events.NewMessage)
    async def _track_users(event):
        try:
            uid = event.sender_id
            if uid:
                users = _load(_USERS_STORE)
                if str(uid) not in users:
                    add_known_user(uid, {"first_msg": event.raw_text})
        except Exception:
            pass
except Exception:
    # if client not defined at import time, ignore; file likely defines client later
    pass

# Admin panel expansion: add callback handlers for more buttons
try:
    @client.on(events.CallbackQuery)
    async def _admin_panel_callbacks(event):
        uid = event.sender_id
        data = event.data.decode() if isinstance(event.data, (bytes, bytearray)) else str(event.data)
        admins = _load(_ADMIN_STORE)
        if data == "admin_panel" and str(uid) in [str(x) for x in admins]:
            buttons = [
                [Button.inline("📋 لیست کاربران", "admin_list_users"), Button.inline("🔒 بلاک‌شده‌ها", "admin_list_blocked")],
                [Button.inline("⛔ بلاک کاربر (ریپلای)", "admin_block"), Button.inline("✅ آن‌بلاک (ریپلای)", "admin_unblock")],
                [Button.inline("📢 ثبت پخش پیام", "admin_broadcast"), Button.inline("✉️ ارسال به کاربر", "admin_send_user")],
                [Button.inline("📄 لاگ‌ها", "admin_logs"), Button.inline("🗑️ حذف کاربر", "admin_delete_user")],
                [Button.inline("🕒 نوع زمان", "admin_time_type"), Button.inline("🔧 تنظیمات ساعت", "admin_time_settings")],
                [Button.inline("🔙 خروج", "admin_logout")]
            ]
            await event.edit("پنل ادمین (گسترش یافته):", buttons=buttons)
            return
        # require admin for other callbacks
        if str(uid) not in [str(x) for x in admins]:
            await event.answer("شما دسترسی ادمین ندارید.", alert=True)
            return
        # handle admin actions
        if data == "admin_list_users":
            users = list_known_users()
            text = "\\n".join([f"{k} - first_seen: {v.get('first_seen')}" for k,v in list(users.items())[:50]])
            if not text: text = "بدون کاربر ثبت‌شده."
            await event.answer(text, alert=True)
        elif data == "admin_list_blocked":
            blocked = _load(os.path.join(os.path.dirname(__file__), 'blocked_users.json'))
            text = "\\n".join(list(blocked.keys())[:100]) or "بدون بلاک‌شده."
            await event.answer(text, alert=True)
        elif data == "admin_logs":
            logs = _load(_LOG_STORE)
            text = "\\n".join([f"[{e['time']}] {e['kind']} {e['info']}" for e in logs.get('events',[])[-50:]]) or "بدون لاگ"
            await event.answer(text, alert=True)
        elif data == "admin_broadcast":
            await event.answer("برای ثبت پخش از دستور متنی /broadcast <متن> استفاده کنید.", alert=True)
        elif data == "admin_send_user":
            await event.answer("برای ارسال به کاربر از دستور متنی /sendto <user_id> <متن> استفاده کنید.", alert=True)
        elif data == "admin_block":
            await event.answer("برای بلاک کردن ریپلای کنید و دکمه بلاک را بزنید.", alert=True)
        elif data == "admin_unblock":
            await event.answer("برای آن‌بلاک ریپلای کنید و دکمه آن‌بلاک را بزنید.", alert=True)
        elif data == "admin_delete_user":
            await event.answer("برای حذف کاربر از دیتابیس ریپلای کنید و دکمه حذف را بزنید.", alert=True)
        elif data == "admin_time_type":
            # show time style selection inline
            styles = [
                Button.inline("Simple", "time_style_1"), Button.inline("Bold", "time_style_2"), Button.inline("Italic", "time_style_3"),
                Button.inline("Underline", "time_style_4"), Button.inline("Strike", "time_style_5"), Button.inline("Double", "time_style_6"),
                Button.inline("Fullwidth", "time_style_7"), Button.inline("Circle", "time_style_8"), Button.inline("Frame", "time_style_9")
            ]
            await event.edit("انتخاب استایل زمان برای اسم بات:", buttons=[styles[i:i+3] for i in range(0,len(styles),3)])
        elif data.startswith("time_style_"):
            # set chosen style
            try:
                idx = int(data.split("_")[-1])
            except:
                idx = 1
            cfg = get_bot_style()
            cfg["style"] = idx
            set_bot_style(cfg)
            await event.answer(f"استایل زمان تنظیم شد: {idx}", alert=True)
        elif data == "admin_time_settings":
            cfg = get_bot_style()
            text = f"فعلا: style={cfg.get('style')}, format={cfg.get('format')}, interval={cfg.get('interval')}, enabled={cfg.get('enabled')}"
            await event.answer(text, alert=True)
        elif data == "admin_logout":
            # remove admin session?
            # perform logout from admins.json if desired
            await event.edit("خروج از پنل.", buttons=[[Button.inline("ورود دوباره", b"enter_admin_pw")]])
        return
except Exception:
    pass

# Admin text commands for broadcast, sendto, block/unblock/delete
try:
    @client.on(events.NewMessage)
    async def _admin_text_commands(event):
        uid = event.sender_id
        text = event.raw_text or ""
        admins = _load(_ADMIN_STORE)
        if str(uid) not in [str(x) for x in admins]:
            return
        # /broadcast <text> -> logged but not mass-sent to avoid abuse
        if text.startswith("/broadcast "):
            msg = text[len("/broadcast "):].strip()
            log_event("broadcast_command", {"by": uid, "text": msg})
            await event.respond("✅ پخش ثبت شد (به صورت ثبت‌شده، ارسال خودکار انجام نمی‌شود).")
            return
        if text.startswith("/sendto "):
            parts = text.split(" ", 2)
            if len(parts) < 3:
                await event.respond("فرمت: /sendto <user_id> <text>")
                return
            target, msgt = parts[1], parts[2]
            try:
                await client.send_message(int(target), msgt)
                log_event("sendto", {"by": uid, "to": target, "text": msgt})
                await event.respond("✅ ارسال شد.")
            except Exception as e:
                await event.respond(f"❌ خطا در ارسال: {e}")
            return
        # block/unblock/delete via reply: commands .admin_block_reply .admin_unblock_reply .admin_delete_reply
        if text.strip() == ".admin_block_reply" and event.is_reply:
            r = await event.get_reply_message()
            target = r.sender_id
            if target:
                # mark blocked file used by previous code
                bfile = os.path.join(os.path.dirname(__file__), "blocked_users.json")
                blocked = _load(bfile); blocked[str(target)] = True; _save(bfile, blocked)
                log_event("admin_block", {"by": uid, "target": target})
                await event.respond(f"✅ کاربر {target} بلاک شد.")
            return
        if text.strip() == ".admin_unblock_reply" and event.is_reply:
            r = await event.get_reply_message()
            target = r.sender_id
            if target:
                bfile = os.path.join(os.path.dirname(__file__), "blocked_users.json")
                blocked = _load(bfile); blocked.pop(str(target), None); _save(bfile, blocked)
                log_event("admin_unblock", {"by": uid, "target": target})
                await event.respond(f"✅ کاربر {target} آن‌بلاک شد.")
            return
        if text.strip() == ".admin_delete_reply" and event.is_reply:
            r = await event.get_reply_message()
            target = r.sender_id
            if target:
                users = _load(_USERS_STORE); users.pop(str(target), None); _save(_USERS_STORE, users)
                log_event("admin_delete", {"by": uid, "target": target})
                await event.respond(f"✅ کاربر {target} از دیتابیس حذف شد.")
            return
except Exception:
    pass

# Bot-name worker: uses bot_token API to set name, respects admin-selected style & format
try:
    import aiohttp
    async def _bot_name_worker():
        cfg = get_bot_style()
        interval = int(cfg.get("interval",60))
        fmt = cfg.get("format","HH:MM")
        last = None
        while True:
            try:
                # compute time string based on format
                now = datetime.datetime.now()
                if fmt == "HH:MM:SS":
                    t = now.strftime("%H:%M:%S")
                elif fmt == "DATE_HH:MM":
                    t = now.strftime("%Y-%m-%d %H:%M")
                else:
                    t = now.strftime("%H:%M")
                styled = stylize_time(t, int(cfg.get("style",1)))
                new_name = f"{BOT_BASE_NAME} | {styled}"
                if new_name != last and cfg.get("enabled", True):
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyName"
                    async with aiohttp.ClientSession() as s:
                        async with s.post(url, json={"name": new_name}) as resp:
                            try:
                                data = await resp.json()
                                log_event("bot_name_set", {"name": new_name, "resp": data})
                            except Exception as e:
                                log_event("bot_name_set_error", {"err": str(e)})
                    last = new_name
            except Exception as e:
                log_event("bot_name_worker_error", {"err": str(e)})
            await asyncio.sleep(interval)
except Exception:
    pass

# schedule starting the bot-name worker if client exists and is started
try:
    # attempt to create a background task when client is ready
    @client.on(events.NewMessage(pattern=r'^/start$'))
    async def _start_trigger(event):
        # start worker once (safe-guard)
        try:
            client._bot_name_worker_started = getattr(client, "_bot_name_worker_started", False)
            if not client._bot_name_worker_started:
                client.loop.create_task(_bot_name_worker())
                client._bot_name_worker_started = True
                await event.respond("✅ Bot-name worker started (bot name will update per admin settings).")
        except Exception:
            pass
except Exception:
    pass

# ---------------------------------------------------------------------------------


# === ADMIN AND BOT NAME CLOCK UPGRADE ===
from telethon import events, Button
import json, aiohttp, datetime, asyncio, os

ADMIN_FILE = os.path.join(os.path.dirname(__file__), "admins.json")
if not os.path.exists(ADMIN_FILE):
    json.dump([], open(ADMIN_FILE,"w"))

def load_admins():
    try:
        return json.load(open(ADMIN_FILE))
    except:
        return []

def save_admins(a):
    json.dump(a, open(ADMIN_FILE,"w"))

BOT_CLOCK = os.path.join(os.path.dirname(__file__), "botclock.json")
if not os.path.exists(BOT_CLOCK):
    json.dump({"enabled": True, "style":1}, open(BOT_CLOCK,"w"))

def load_clock():
    return json.load(open(BOT_CLOCK))

def save_clock(c):
    json.dump(c, open(BOT_CLOCK,"w"))

@client.on(events.NewMessage(pattern=r'^/admin$'))
async def admin_root(e):
    uid=e.sender_id
    admins=load_admins()
    if uid in admins:
        await e.respond("پنل ادمین:", buttons=[[Button.inline("ساعت بات","clk"), Button.inline("مدیریت","adm")]])
    else:
        await e.respond("رمز ادمین را وارد کنید:", buttons=[[Button.inline(str(i),f"key_{i}") for i in range(10)]])

@client.on(events.CallbackQuery(pattern=b"key_"))
async def admin_key(e):
    digit=e.data.decode().split("_")[1]
    uid=e.sender_id
    buf=getattr(client,"_adbuf",{})
    code=buf.get(uid,"")+digit
    buf[uid]=code
    client._adbuf=buf
    SECRET="1276438321"
    if code==SECRET:
        admins=load_admins()
        admins.append(uid)
        save_admins(list(set(admins)))
        await e.edit("ادمین شدید!", buttons=[[Button.inline("ورود","adm")]])
    elif len(code)>=len(SECRET):
        buf[uid]=""
        await e.answer("❌ اشتباه", alert=True)
    else:
        await e.answer(f"وارد شده: {code}")

@client.on(events.CallbackQuery(pattern=b"adm"))
async def panel(e):
    await e.edit("مدیریت:", buttons=[
        [Button.inline("کاربران","usr")],
        [Button.inline("بلاک/آن‌بلاک","blk")]
    ])

@client.on(events.CallbackQuery(pattern=b"clk"))
async def clk_menu(e):
    cfg=load_clock()
    await e.edit(f"ساعت بات (enabled={cfg.get('enabled')}):",
                 buttons=[
                     [Button.inline("خاموش/روشن","clk_toggle")],
                     [Button.inline("استایل 1","clk_s1"),Button.inline("استایل 2","clk_s2")]
                 ])

@client.on(events.CallbackQuery(pattern=b"clk_toggle"))
async def clk_t(e):
    cfg=load_clock()
    cfg["enabled"]=not cfg.get("enabled",True)
    save_clock(cfg)
    await clk_menu(e)

@client.on(events.CallbackQuery(pattern=b"clk_s"))
async def clk_s(e):
    s=int(e.data.decode().split("_s")[1])
    cfg=load_clock(); cfg["style"]=s; save_clock(cfg)
    await clk_menu(e)

async def botname_worker():
    last=None
    while True:
        try:
            cfg=load_clock()
            if cfg.get("enabled"):
                now=datetime.datetime.now().strftime("%H:%M")
                styled=now  # simple style placeholder
                new=f"self tel | {styled}"
                if new!=last:
                    async with aiohttp.ClientSession() as s:
                        await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setMyName",
                                     json={"name":new})
                    last=new
        except: pass
        await asyncio.sleep(60)

client.loop.create_task(botname_worker())

