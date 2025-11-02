#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import time
import datetime
import base64
import zipfile
from io import BytesIO
import streamlit as st
import pandas as pd
import plotly.express as px
from backend import DatabaseManager, AuthService, InvoiceExtractor, InvoiceService, SystemService, ExportService, User, \
    logger
from classification import classify_pdfs, move_to_output

# 设置页面配置
st.set_page_config(
    page_title="智能发票提取系统",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded"
)


# 应用自定义样式
def apply_custom_styles():
    st.markdown("""
    <style>
        /* 主容器响应式布局 */
        .stApp {
            background-color: #f8f9fa;
            font-family: 'Microsoft YaHei', Arial, sans-serif;
        }

        /* 侧边栏样式 */
        section[data-testid="stSidebar"] {
            background: linear-gradient(135deg, #6a8fcc 0%, #7a9fdc 100%);
            min-width: 280px !important;
            max-width: 320px !important;
        }

        .sidebar-content {
            color: white;
            padding: 10px;
        }

        .sidebar-title {
            color: white !important;
            font-weight: 800 !important;
            font-size: 30px !important;
            text-align: center;
            margin-bottom: 2px;
        }

        .sidebar-subtitle {
            color: #e8f4fd !important;
            font-size: 18px !important;
            text-align: center;
            opacity: 0.9;
            margin-bottom: 15px;
        }

        /* 主内容区域样式 */
        .main-content {
            padding: 40px;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            border-radius: 15px;
            margin: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);
            color: white;
            text-align: center;
            min-height: 300px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }

        .main-title {
            font-size: 36px;
            font-weight: 800;
            color: white;
            margin-bottom: 20px;
            text-shadow: 0 2px 10px rgba(0,0,0,0.3);
            font-family: 'Microsoft YaHei', Arial, sans-serif;
        }

        .subtitle {
            font-size: 18px;
            color: rgba(255,255,255,0.9);
            font-weight: 400;
            line-height: 1.6;
            max-width: 600px;
            margin: 0 auto;
            font-family: 'Microsoft YaHei', Arial, sans-serif;
        }

        /* 控制按钮样式 */
        .control-buttons {
            display: flex;
            gap: 10px;
            margin: 20px 0;
        }

        .control-button {
            padding: 10px 20px;
            border-radius: 8px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .primary-button {
            background: #e74c3c;
            color: white;
        }

        .secondary-button {
            background: #3498db;
            color: white;
        }

        .warning-button {
            background: #f39c12;
            color: white;
        }

        .control-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }

        /* 结果表格样式 */
        .result-table {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* Token状态样式 */
        .token-status {
            background: rgba(255,255,255,0.1);
            border-radius: 6px;
            padding: 8px 12px;
            margin: 5px 0;
            border-left: 3px solid #2ecc71;
        }
        .token-expiring {
            border-left-color: #f39c12;
            background: rgba(243, 156, 18, 0.1);
        }
        .token-expired {
            border-left-color: #e74c3c;
            background: rgba(231, 76, 60, 0.1);
        }
        .token-time {
            font-size: 12px;
            opacity: 0.8;
            margin-top: 2px;
        }
        /* 分类页面样式 */
        .classification-section {
            margin-top: 30px;
        }

        .category-list {
            margin-top: 20px;
        }

        .category-item {
            margin-bottom: 10px;
        }

        .download-button {
            margin-right: 10px;
        }
    </style>
    """, unsafe_allow_html=True)


apply_custom_styles()


class FrontendApp:
    """前端应用类 - 支持中断处理和状态保持"""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.auth_service = AuthService(self.db_manager)
        self.extractor = InvoiceExtractor()
        self.invoice_service = InvoiceService(self.db_manager, self.extractor)
        self.system_service = SystemService(self.db_manager)
        self.export_service = ExportService()
        self._init_token_from_url()  # 从URL初始化Token
        self._init_session_state()  # 初始化会话状态
        self._init_time_management_state()  # 初始化时间管理状态
        self.classification_service = ClassificationService()

    def classification_page(self):
        """分类管理页面"""
        st.title("📁 发票分类管理")

        # 输入文件夹路径
        st.markdown("### 📂 选择包含PDF文件的文件夹")
        folder_path = st.text_input(
            "请输入包含PDF文件的文件夹完整路径",
            value=self.db_manager.folder_path if hasattr(self.db_manager, 'folder_path') else "",
            placeholder="例如：C:/Users/发票文件 或 ./invoices",
            help="请输入包含PDF发票文件的文件夹完整路径",
            label_visibility="collapsed"
        )

        if folder_path:
            if os.path.exists(folder_path):
                pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
                if pdf_files:
                    st.success(f"✅ 找到 {len(pdf_files)} 个PDF文件")
                else:
                    st.warning("⚠️ 文件夹中没有找到PDF文件")
            else:
                st.error("❌ 文件夹路径不存在")

        # 开始分类按钮
        if st.button("🚀 开始分类", type="primary", use_container_width=True):
            if not folder_path:
                st.error("请先输入文件夹路径")
                return

            if not os.path.exists(folder_path):
                st.error("输入的文件夹路径不存在")
                return

            # 调用分类函数
            self.system_service.log_operation(
                st.session_state.user_id, "开始分类", f"开始对文件夹 '{folder_path}' 中的发票进行分类"
            )
            st.info("🔄 正在分类文件，请稍候...")

            try:
                temp_output = classify_pdfs(folder_path)
                move_to_output(temp_output)
                self.system_service.log_operation(
                    st.session_state.user_id, "分类完成", f"成功对文件夹 '{folder_path}' 中的发票进行分类"
                )
                st.success("✅ 分类完成！分类结果已移动到 'output' 文件夹。")
            except Exception as e:
                self.system_service.log_operation(
                    st.session_state.user_id, "分类失败", f"对文件夹 '{folder_path}' 中的发票分类失败: {str(e)}"
                )
                st.error(f"❌ 分类过程中出现错误: {str(e)}")

        # 显示分类结果（可选）
        if os.path.exists("output"):
            st.subheader("📊 分类结果概览")
            categories = os.listdir("output")
            if categories:
                for category in categories:
                    files = os.listdir(os.path.join("output", category))
                    st.markdown(f"#### {category} ({len(files)} 个文件)")
                    # 提供下载链接
                    zip_filename = f"{category}.zip"
                    if st.button(f"📥 下载 {category} 分类结果", key=f"download_{category}"):
                        self._create_zip(os.path.join("output", category), zip_filename)
                        st.download_button(
                            label=f"下载 {category} 分类结果",
                            data=open(zip_filename, "rb").read(),
                            file_name=zip_filename,
                            mime="application/zip"
                        )
                        # 删除生成的ZIP文件
                        os.remove(zip_filename)
            else:
                st.info("📁 'output' 文件夹中暂无分类结果。")

    def _create_zip(self, source_dir, output_filename):
        """创建ZIP文件"""
        with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    zipf.write(os.path.join(root, file),
                               os.path.relpath(os.path.join(root, file),
                                               os.path.join(source_dir, '..')))
        print(f"ZIP文件 '{output_filename}' 创建成功。")

    def _init_time_management_state(self):
        """修复版本：初始化时间管理状态"""
        # 确保所有必要的状态都存在
        if 'last_time_update' not in st.session_state:
            st.session_state.last_time_update = time.time()
        if 'time_display' not in st.session_state:
            st.session_state.time_display = "计算中..."
        if 'token_status' not in st.session_state:
            st.session_state.token_status = "🟢 有效"
        if 'time_color' not in st.session_state:
            st.session_state.time_color = "#27ae60"
        if 'last_manual_refresh' not in st.session_state:
            st.session_state.last_manual_refresh = 0
        if 'auto_refresh_enabled' not in st.session_state:
            st.session_state.auto_refresh_enabled = True
        if 'refresh_interval' not in st.session_state:
            st.session_state.refresh_interval = 5  # 默认5秒
        if 'time_management_initialized' not in st.session_state:
            st.session_state.time_management_initialized = True

    def _calculate_time_display(self):
        """计算并更新时间显示"""
        expire_time_str = st.session_state.get('token_expire_time')
        if not expire_time_str:
            st.session_state.time_display = "未知"
            st.session_state.token_status = "🔴 错误"
            st.session_state.time_color = "#e74c3c"
            return

        try:
            expire_time = datetime.datetime.fromisoformat(expire_time_str)
            now = datetime.datetime.now()
            time_left = expire_time - now

            if time_left.total_seconds() <= 0:
                st.session_state.time_display = "00:00:00"
                st.session_state.token_status = "🔴 已过期"
                st.session_state.time_color = "#e74c3c"
                return

            hours = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)
            seconds = int(time_left.total_seconds() % 60)

            st.session_state.time_display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            if hours < 1:
                st.session_state.token_status = "🟠 即将过期"
                st.session_state.time_color = "#f39c12"
            else:
                st.session_state.token_status = "🟢 有效"
                st.session_state.time_color = "#27ae60"

        except Exception as e:
            logger.error(f"时间计算错误: {e}")
            st.session_state.time_display = "计算错误"
            st.session_state.token_status = "🔴 错误"
            st.session_state.time_color = "#e74c3c"

    def _should_update_time(self):
        """判断是否需要更新时间"""
        if not st.session_state.get('auto_refresh_enabled', True):
            return False

        current_time = time.time()
        refresh_interval = st.session_state.get('refresh_interval', 5)
        return current_time - st.session_state.last_time_update >= refresh_interval

    def _update_time_display(self):
        """修复版本：更新时间显示（条件性更新）"""
        if self._should_update_time():
            self._calculate_time_display()
            st.session_state.last_time_update = time.time()
            return True
        return False

    def _render_token_display(self):
        """渲染Token显示区域"""
        # 从Session State获取数据
        time_display = st.session_state.get('time_display', '计算中...')
        token_status = st.session_state.get('token_status', '有效')
        refresh_interval = st.session_state.get('refresh_interval', 5)

        # 根据状态设置颜色
        if token_status == "有效":
            status_color = "#27ae60"
        elif "即将" in token_status:
            status_color = "#f39c12"
        else:  # 过期或其他状态
            status_color = "#e74c3c"

        st.markdown(f"""
           <div style="
               background: rgba(255,255,255,0.1); 
               border-radius: 10px; 
               padding: 15px; 
               margin: 15px 0;
               border-left: 4px solid {status_color};
           ">
               <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                   <span style="font-size: 14px;">Token状态:</span>
                   <span style="color: {status_color}; font-weight: bold;">{token_status}</span>
               </div>

               <div style="text-align: center; font-size: 12px; opacity: 0.8; margin-bottom: 5px;">
                   剩余时间
               </div>

               <div style="
                   font-family: 'Courier New', monospace;
                   font-size: 20px;
                   font-weight: bold;
                   text-align: center;
                   background: rgba(0,0,0,0.3);
                   padding: 10px;
                   border-radius: 8px;
                   margin: 8px 0;
                   color: {status_color};
                   letter-spacing: 2px;
               ">{time_display}</div>

               <div class="refresh-control">
                   <div style="flex: 1; text-align: center;">
                       <span style="font-size: 10px; opacity: 0.6;">
                           ⏰ 每{refresh_interval}秒更新显示
                       </span>
                   </div>
               </div>
           </div>
           """, unsafe_allow_html=True)

        # 手动刷新按钮
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("↻", key="mini_refresh", help="快速刷新时间显示"):
                self._manual_refresh_time()

    def _init_token_from_url(self):
        """从URL参数初始化Token"""
        # 获取URL中的token参数
        params = st.query_params.to_dict()
        token = params.get('token')

        if token and 'auth_token' not in st.session_state:
            # 将URL中的Token保存到session state
            st.session_state.auth_token = token
            # 设置默认过期时间（24小时后）
            expire_time = datetime.datetime.now() + datetime.timedelta(hours=24)
            st.session_state.token_expire_time = expire_time.isoformat()

            # 立即验证Token
            if self._check_token_validity():
                st.success("🔄 从URL自动登录成功！")

    def _init_session_state(self):
        """初始化会话状态- 修复Token持久化"""
        # 从URL参数获取Token（防止刷新丢失）
        params = st.query_params.to_dict()
        if 'token' in params and 'auth_token' not in st.session_state:
            st.session_state.auth_token = params['token']
        # 检查Token有效性
        if 'auth_token' in st.session_state and not st.session_state.get('logged_in'):
            self._check_token_validity()
        if 'logged_in' not in st.session_state:
            st.session_state.logged_in = False
        if 'user_id' not in st.session_state:
            st.session_state.user_id = None
        if 'username' not in st.session_state:
            st.session_state.username = None
        if 'auth_token' not in st.session_state:
            st.session_state.auth_token = None
        if 'token_expire_time' not in st.session_state:
            st.session_state.token_expire_time = None
        if 'uploaded_files' not in st.session_state:
            st.session_state.uploaded_files = []
        if 'current_results' not in st.session_state:
            st.session_state.current_results = []
        if 'processing' not in st.session_state:
            st.session_state.processing = False
        if 'paused' not in st.session_state:
            st.session_state.paused = False
        if 'current_file_index' not in st.session_state:
            st.session_state.current_file_index = 0
        if 'file_paths' not in st.session_state:
            st.session_state.file_paths = []
        if 'file_source' not in st.session_state:
            st.session_state.file_source = "upload"
        if 'folder_path' not in st.session_state:
            st.session_state.folder_path = ""

    def add_enhanced_time_management(self):
        """增强的时间管理功能"""
        with st.sidebar:
            if st.session_state.get('logged_in'):
                st.markdown("---")
                st.markdown("### ⚙️ 时间设置")

                # 自动刷新开关
                auto_refresh = st.checkbox(
                    "🔄 启用自动刷新",
                    value=st.session_state.get('auto_refresh_enabled', True),
                    key="auto_refresh_checkbox",
                    help="启用后自动更新时间显示"
                )
                st.session_state.auto_refresh_enabled = auto_refresh

                if auto_refresh:
                    # 刷新间隔设置
                    refresh_interval = st.slider(
                        "刷新间隔(秒)",
                        min_value=1,
                        max_value=60,
                        value=st.session_state.get('refresh_interval', 5),
                        key="refresh_interval_slider",
                        help="时间显示更新频率"
                    )
                    st.session_state.refresh_interval = refresh_interval
                    st.success(f"✅ 已设置：每{refresh_interval}秒更新时间显示")
                else:
                    st.info("⏸️ 自动更新已关闭")

                # 时间详情展开面板
                with st.expander("📊 时间详情", expanded=False):
                    expire_time = st.session_state.get('token_expire_time', '未知')
                    current_display = st.session_state.get('time_display', '计算中...')

                    st.write(f"**Token过期时间:** {expire_time}")
                    st.write(f"**当前显示时间:** {current_display}")
                    st.write(
                        f"**最后更新时间:** {datetime.datetime.fromtimestamp(st.session_state.last_time_update).strftime('%H:%M:%S')}")

                    # 手动控制按钮
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("🔄 立即刷新", use_container_width=True):
                            self._manual_refresh_time()
                    with col2:
                        if st.button("📊 更新状态", use_container_width=True):
                            self._update_time_status_only()

    def _conditional_time_update(self):
        """
        条件性时间更新 - 不自动刷新页面
        图片中的'刷新间隔'设置用于控制显示的更新频率，而非页面刷新
        """
        if not st.session_state.get('logged_in'):
            return

        current_time = time.time()
        # 使用图片中设置的刷新间隔（默认5秒）
        refresh_interval = st.session_state.get('refresh_interval', 5)

        # 只在需要时更新时间显示，但不强制刷新页面
        if current_time - st.session_state.last_time_update >= refresh_interval:
            self._calculate_time_display()
            st.session_state.last_time_update = current_time
            # 关键：不调用st.rerun()，避免界面闪烁

    def _check_token_validity(self) -> bool:
        """检查Token是否有效"""
        token = st.session_state.get('auth_token')
        if not token:
            return False

        try:
            # 验证Token
            payload = self.auth_service.verify_token(token)
            if not payload:
                return False

            # 检查过期时间
            if 'token_expire_time' not in st.session_state:
                # 如果没有过期时间，设置一个默认值
                expire_time = datetime.datetime.now() + datetime.timedelta(hours=24)
                st.session_state.token_expire_time = expire_time.isoformat()
            else:
                expire_time = datetime.datetime.fromisoformat(st.session_state.token_expire_time)
                if datetime.datetime.now() > expire_time:
                    return False

            # 更新用户信息
            st.session_state.user_id = payload.get('user_id')
            st.session_state.username = payload.get('username')
            st.session_state.logged_in = True

            #  # 确保URL中包含Token（防止刷新丢失）
            if st.query_params.get("token") != token:
                st.query_params["token"] = token

            logger.info(f"✅ Token验证成功，用户: {st.session_state.username}")
            return True

        except Exception as e:
            logger.error(f"Token验证错误: {e}")
            return False

    def _clear_auth_data(self):
        """清除认证数据 - 同时清除查询参数"""
        # 清除session state
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.auth_token = None
        st.session_state.token_expire_time = None

        # 关键修复：清除URL中的Token参数
        if "token" in st.query_params:
            del st.query_params["token"]

        logger.info("✅ 认证数据已清除")

    def _save_auth_data(self, user: User, token: str):
        """保存认证数据"""
        expire_time = datetime.datetime.now() + datetime.timedelta(hours=24)

        st.session_state.logged_in = True
        st.session_state.user_id = user.id
        st.session_state.username = user.username
        st.session_state.auth_token = token
        st.session_state.token_expire_time = expire_time.isoformat()

        # 关键修复：将Token保存到URL参数
        st.query_params["token"] = token

        logger.info(f"✅ 认证数据已保存，用户: {user.username}")
        logger.info(f"Token生成成功，过期时间: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}")

    def _auto_refresh_token(self):
        """自动刷新Token"""
        if not st.session_state.get('auth_token'):
            return

        # 检查Token剩余时间
        if st.session_state.get('token_expire_time'):
            expire_time = datetime.datetime.fromisoformat(st.session_state.token_expire_time)
            time_left = expire_time - datetime.datetime.now()

            # 如果剩余时间少于30分钟，自动刷新
            if time_left.total_seconds() < 1800:
                try:
                    # 生成新Token
                    new_token = self.auth_service.generate_token(
                        st.session_state.user_id,
                        st.session_state.username
                    )
                    new_expire_time = datetime.datetime.now() + datetime.timedelta(hours=24)

                    # 更新Token
                    st.session_state.auth_token = new_token
                    st.session_state.token_expire_time = new_expire_time.isoformat()
                    st.experimental_set_query_params(token=new_token)

                    # 记录刷新日志
                    self.system_service.log_operation(
                        st.session_state.user_id,
                        "Token自动刷新",
                        "Token已自动刷新"
                    )

                    st.toast("🔐 Token已自动刷新", icon="✅")
                    logger.info(f"Token自动刷新，新过期时间: {new_expire_time.strftime('%H:%M:%S')}")

                except Exception as e:
                    logger.error(f"Token自动刷新失败: {e}")

    def login_page(self):
        """登录页面"""
        st.title("🔐 系统登录")

        # 先检查是否有有效的Token
        if self._check_token_validity():
            st.success("🔄 自动登录成功！")
            time.sleep(0.5)
            st.rerun()
            return

        with st.form("login_form"):
            username = st.text_input("👤 用户名", placeholder="请输入用户名")
            password = st.text_input("🔒 密码", type="password", placeholder="请输入密码")

            col1, col2 = st.columns([2, 1])
            with col1:
                submitted = st.form_submit_button("🚀 登录", use_container_width=True)
            with col2:
                if st.form_submit_button("🔄 重置", use_container_width=True):
                    st.rerun()

            if submitted:
                if not username or not password:
                    st.error("❌ 请输入用户名和密码")
                    return

                user = self.auth_service.verify_user(username, password)
                if user:
                    # 生成Token
                    token = self.auth_service.generate_token(user.id, user.username)

                    # 保存认证数据（会同时保存到session和URL）
                    self._save_auth_data(user, token)

                    # 记录登录日志
                    self.system_service.log_operation(
                        user.id, "用户登录", f"用户 {username} 登录系统"
                    )

                    st.success("✅ 登录成功！Token已生成")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ 用户名或密码错误")

    def create_sidebar(self):
        """创建侧边栏 - 集成JavaScript计时器"""
        with st.sidebar:
            # 标题区域
            st.markdown("""
            <div class="sidebar-content">
                <h1 class="sidebar-title">🧾 发票系统</h1>
                <p class="sidebar-subtitle">智能发票提取分析平台</p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")

            # 在用户信息区域 - 使用Session State局部更新
            if st.session_state.get('logged_in'):
                # 渲染Token显示（会自动更新时间）
                # self._render_token_display()
                # 添加增强时间管理
                # self.add_enhanced_time_management()
                # 显示用户名信息
                st.markdown(f"""
                           <div style="color: white; text-align: center; margin: 10px 0;">
                               <div style="font-size: 14px;">欢迎, {st.session_state.username}</div>
                           </div>
                           """, unsafe_allow_html=True)

            # 功能选择区域
            st.markdown("### 📋 选择功能")

            menu_options = {
                "发票提取": {"icon": "📁", "desc": "批量提取发票信息"},
                "结果查看": {"icon": "📊", "desc": "查看处理结果"},
                "数据分析": {"icon": "📈", "desc": "数据可视化分析"},
                "系统设置": {"icon": "⚙️", "desc": "系统配置管理"},
                "使用帮助": {"icon": "❓", "desc": "使用说明文档"},
                "分类管理": {"icon": "🗂️", "desc": "发票文件分类管理"},
            }

            selected = st.radio(
                "导航菜单",
                options=list(menu_options.keys()),
                format_func=lambda x: f"{menu_options[x]['icon']} {x}",
                label_visibility="collapsed"
            )

            # 功能描述
            st.markdown(f"""
            <div class="function-desc">
                <div class="desc-text">{menu_options[selected]['desc']}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")

            # 系统状态区域
            st.markdown("### 📊 系统状态")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("处理文件", len(st.session_state.current_results))
            with col2:
                success_count = len([r for r in st.session_state.current_results if r.get('状态') == '成功'])
                total_count = len(st.session_state.current_results)
                success_rate = (success_count / total_count * 100) if total_count > 0 else 0
                st.metric("成功率", f"{success_rate:.1f}%")

            st.markdown("---")
            # 退出登录按钮 -  清除Token
            if st.session_state.get('logged_in'):
                if st.button("🚪 退出登录", use_container_width=True):
                    # 记录退出日志
                    self.system_service.log_operation(
                        st.session_state.user_id, "用户退出", f"用户 {st.session_state.username} 退出系统"
                    )
                    # 清除认证数据
                    self._clear_auth_data()
                    st.rerun()

            return selected

    def _manual_refresh_time(self):
        """手动刷新时间"""
        self._calculate_time_display()
        st.session_state.last_time_update = time.time()
        st.rerun()

    def _update_time_status_only(self):
        """只更新时间状态，不刷新页面"""
        self._calculate_time_display()
        st.session_state.last_time_update = time.time()

    def invoice_extraction_page(self):
        """发票提取页面 - 支持中断处理"""
        st.title("📁 发票批量提取")

        # 使用选项卡布局
        tab1, tab2 = st.tabs(["📤 上传文件", "📂 文件夹处理"])

        with tab1:
            self._file_upload_section()

        with tab2:
            self._folder_processing_section()

        # 处理选项区域
        self._processing_options_section()

        # 控制按钮区域
        self._control_buttons_section()

        # 处理进度显示
        if st.session_state.processing:
            self._show_processing_progress()

        # 显示当前处理结果
        if st.session_state.current_results:
            self._show_current_results_advanced()

    def _control_buttons_section(self):
        """控制按钮区域 - 添加清除功能"""
        st.markdown("### ⚙️ 处理控制")

        # 第一行：主要操作按钮
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            start_disabled = st.session_state.processing
            if st.button("🚀 开始处理", type="primary", use_container_width=True,
                         disabled=start_disabled, key="start_button"):
                self._start_processing()

        with col2:
            # 只有在处理中且未暂停时才可点击
            pause_disabled = not st.session_state.processing or st.session_state.paused
            if st.button("⏸️ 暂停处理",
                         type="secondary",
                         use_container_width=True,
                         disabled=pause_disabled,
                         key="pause_button"):
                self._pause_processing()
                # 点击后立即禁用按钮（通过rerun实现）
                st.rerun()

        with col3:
            resume_disabled = not st.session_state.processing or not st.session_state.paused
            if st.button("▶️ 继续处理", type="secondary", use_container_width=True,
                         disabled=resume_disabled, key="resume_button"):
                self._resume_processing()

        with col4:
            stop_disabled = not st.session_state.processing
            if st.button("⏹️ 停止处理", type="secondary", use_container_width=True,
                         disabled=stop_disabled, key="stop_button"):
                self._stop_processing()

        with col5:
            clear_disabled = st.session_state.processing
            if st.button("🗑️ 清除结果", type="secondary", use_container_width=True,
                         disabled=clear_disabled, key="clear_button"):
                self._clear_results()

        # 第二行：状态显示
        if st.session_state.processing:
            if st.session_state.paused:
                st.info("⏸️ **处理状态：已暂停** - 点击'继续处理'恢复")
            else:
                total_files = len(st.session_state.file_paths)
                current_index = st.session_state.current_file_index
                if current_index >= total_files:
                    st.success("✅ **处理状态：已全部完成**")
                else:
                    st.success("🔄 **处理状态：正在处理中...**")
        else:
            if st.session_state.current_results:
                st.info("💡 **处理状态：已完成** - 可以查看结果或清除重新开始")
            else:
                st.info("📋 **处理状态：待开始** - 请选择文件后点击'开始处理'")

    def _clear_results(self):
        """清除当前结果"""
        st.session_state.current_results = []
        st.session_state.file_paths = []
        st.session_state.current_file_index = 0
        st.session_state.uploaded_files = []
        st.session_state.folder_path = ""
        st.success("✅ 结果已清除，可以重新开始")

    def _start_processing(self):
        """开始处理"""
        if st.session_state.file_source == "upload" and not st.session_state.uploaded_files:
            st.warning("⚠️ 请先上传文件")
            return
        elif st.session_state.file_source == "folder" and not st.session_state.folder_path:
            st.warning("⚠️ 请先指定文件夹路径")
            return

        # 准备文件路径
        if st.session_state.file_source == "upload":
            # 创建临时目录保存上传的文件
            temp_dir = "temp_uploads"
            os.makedirs(temp_dir, exist_ok=True)
            file_paths = []
            for uploaded_file in st.session_state.uploaded_files:
                file_path = os.path.join(temp_dir, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                file_paths.append(file_path)
        else:
            # 处理文件夹中的文件
            folder_path = st.session_state.folder_path
            file_paths = []
            for file in os.listdir(folder_path):
                if file.lower().endswith('.pdf'):
                    file_paths.append(os.path.join(folder_path, file))

        if not file_paths:
            st.warning("⚠️ 没有找到可处理的PDF文件")
            return

        # 初始化处理状态
        st.session_state.file_paths = file_paths
        st.session_state.current_file_index = 0
        st.session_state.current_results = []  # 清空之前的结果
        st.session_state.processing = True
        st.session_state.paused = False

        # ---- 新增：读取用户选择的下拉框选项 ----
        selected_bu = st.session_state.get("drop", "未选择事业部")  # 事业部
        selected_project = st.session_state.get("daxiangmu", "未选择大项目")  # 大项目
        selected_year = st.session_state.get("sel_year", "未选择年份")  # 年
        selected_month = st.session_state.get("sel_month", "未选择月份")  # 月

        # 构造费用所属月份字段，如 "2025年9月"
        selected_audit_month = f"{selected_year}年{selected_month}" if selected_year and selected_month else "未选择"

        # 可以存入 session_state 供后续使用，或者直接在处理时引用
        st.session_state.user_selected_options = {
            "事业部": selected_bu,
            "大项目": selected_project,
            "费用所属月份(审核月份)": selected_audit_month,  # 直接存这个组合字段
        }

        # 可以打印看看是否获取到了
        logger.info(
            f"用户选择 - 事业部：{selected_bu}, 大项目：{selected_project}, 年份：{selected_year}, 月份：{selected_month}")

        # 显示文件统计信息
        st.success(f"🎯 开始处理 {len(file_paths)} 个文件...")

    def _pause_processing(self):
        """暂停处理"""
        st.session_state.paused = True

    def _resume_processing(self):
        """继续处理"""
        st.session_state.paused = False

    def _stop_processing(self):
        """停止处理"""
        st.session_state.processing = False
        st.session_state.paused = False
        st.warning("⏹️ 处理已停止")

    def _show_processing_progress(self):
        """显示处理进度 - 修复完成判断逻辑"""
        st.markdown("### 🔄 处理进度")

        if st.session_state.file_paths:
            total_files = len(st.session_state.file_paths)
            current_index = st.session_state.current_file_index
            progress = current_index / total_files if total_files > 0 else 0

            # 进度条
            progress_bar = st.progress(progress)

            # 状态信息
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("总文件数", total_files)
            with col2:
                st.metric("已处理", current_index)
            with col3:
                st.metric("进度", f"{progress:.1%}")

            # 自动处理下一个文件（如果未暂停且未完成）
            if (not st.session_state.paused and
                    st.session_state.current_file_index < total_files):
                self._process_next_file()

    def _process_next_file(self):
        """处理下一个文件 - 处理单个文件逻辑"""
        if st.session_state.current_file_index >= len(st.session_state.file_paths):
            return
        file_path = st.session_state.file_paths[st.session_state.current_file_index]
        try:
            # 1. 处理发票文件 先调用提取器提取发票上的基本信息（自动从PDF提取）
            basic_result = self.extractor.extract_invoice_info(file_path)
            basic_result['姓名'] = self.extractor.extract_person_name(os.path.basename(file_path))
            # 2. ✅ 从 session_state 获取用户手动选择的值
            user_options = st.session_state.get("user_selected_options", {})
            selected_bu = user_options.get("事业部", "未选择事业部")
            selected_project = user_options.get("大项目", "未选择大项目")
            selected_audit_month = user_options.get("费用所属月份(审核月份)", "未选择月份")

            # 3. 关键：将这些用户选择的值，手动添加到 result 字典中
            basic_result['事业部'] = selected_bu
            basic_result['大项目'] = selected_project
            basic_result['费用所属月份(审核月份)'] = selected_audit_month

            # 4. 保存到数据库（直接调用 _save_to_database，传入 user_id）
            if basic_result.get('状态') == '成功':
                self.invoice_service._save_to_database(basic_result, st.session_state.user_id)

            #  5. 添加到当前结果列表（用于前端展示）
            st.session_state.current_results.append(basic_result)

            # 更新进度
            st.session_state.current_file_index += 1
            # 只有当处理完所有文件时才标记完成
            if st.session_state.current_file_index >= len(st.session_state.file_paths):
                st.session_state.processing = False
                st.balloons()
                # 记录完成日志
                success_count = len([r for r in st.session_state.current_results if r.get('状态') == '成功'])
                self.system_service.log_operation(
                    st.session_state.user_id,
                    "批量处理完成",
                    f"成功处理 {success_count}/{len(st.session_state.file_paths)} 个文件"
                )
            # 刷新界面
            st.rerun()
        except Exception as e:
            st.error(f"❌ 处理文件失败: {os.path.basename(file_path)} - {str(e)}")
            st.session_state.current_file_index += 1

    def _show_current_results_advanced(self):
        """显示当前处理结果 - 高级分页版本"""
        st.markdown("### 📋 当前处理结果")

        if not st.session_state.current_results:
            st.info("💡 暂无处理结果")
            return

        # 控制面板
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

        with col1:
            st.markdown(f"**📊 数据统计：共 {len(st.session_state.current_results)} 条记录**")

        with col2:
            items_per_page = st.selectbox(
                "每页显示",
                [10, 20, 50, 100],
                index=1,  # 默认20条
                key="page_size"
            )

        with col3:
            if st.button("🗑️ 清除结果", type="secondary", use_container_width=True):
                self._clear_results()
                st.rerun()

        with col4:
            if st.button("📥 导出全部", type="primary", use_container_width=True):
                self._export_current_results()

        # 创建数据框
        df = pd.DataFrame(st.session_state.current_results)

        # 调整列顺序
        column_order = ['费用所属月份(审核月份)', '事业部', '大项目', '文件名', '姓名', '发票代码', '发票号码',
                        '开票日期', '金额', '税率', '税额', '价税合计', '状态']
        # 然后过滤掉不存在的列（确保代码健壮性）：
        existing_columns = [col for col in column_order if col in df.columns]
        df = df[existing_columns + [col for col in df.columns if col not in existing_columns]]

        # 🔧 新增：固定值下拉框 - 事业部
        fixed_depts = ["第一事业部", "第二事业部", "第三事业部"]
        selected_dept = st.selectbox(
            "选择 事业部:",
            options=["全部"] + fixed_depts,
            index=0,  # 默认选择“全部”
            key="filter_dept"
        )

        # 🔧 新增：固定值下拉框 - 大项目
        fixed_projects = ["深圳网优代维项目", "河源网优代维项目"]
        selected_project = st.selectbox(
            "选择 大项目:",
            options=["全部"] + fixed_projects,
            index=0,  # 默认选择“全部”
            key="filter_project"
        )

        # 🔧 新增：固定值下拉框 - 费用所属月份(审核月份)
        # 获取所有唯一的费用所属月份
        unique_months = sorted(list(set(
            [r.get('费用所属月份_审核月份') for r in st.session_state.current_results
             if r.get('费用所属月份_审核月份') is not None]
        )))

        # 分页计算
        total_pages = max(1, (len(df) + items_per_page - 1) // items_per_page)

        # 分页导航
        if total_pages > 1:
            # 页码选择器
            col1, col2, col3 = st.columns([1, 3, 1])
            with col2:
                page_options = list(range(1, total_pages + 1))
                page = st.selectbox(
                    "选择页码",
                    options=page_options,
                    format_func=lambda x: f"第 {x} 页（共 {total_pages} 页）",
                    key="result_page_selector"
                ) - 1

            # 快速导航按钮
            nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns(5)

            with nav_col1:
                if st.button("⏮️ 首页", use_container_width=True, disabled=page == 0):
                    st.session_state.current_page = 0
                    st.rerun()

            with nav_col2:
                if st.button("◀️ 上一页", use_container_width=True, disabled=page == 0):
                    st.session_state.current_page = max(0, page - 1)
                    st.rerun()

            with nav_col3:
                st.markdown(f"**第 {page + 1} 页**", help=f"共 {total_pages} 页")

            with nav_col4:
                if st.button("▶️ 下一页", use_container_width=True, disabled=page >= total_pages - 1):
                    st.session_state.current_page = min(total_pages - 1, page + 1)
                    st.rerun()

            with nav_col5:
                if st.button("⏭️ 末页", use_container_width=True, disabled=page >= total_pages - 1):
                    st.session_state.current_page = total_pages - 1
                    st.rerun()
        else:
            page = 0

        # 显示当前页数据
        start_idx = page * items_per_page
        end_idx = min((page + 1) * items_per_page, len(df))

        st.dataframe(
            df.iloc[start_idx:end_idx],
            use_container_width=True,
            height=min(600, items_per_page * 35)  # 动态调整高度
        )

        # 分页信息
        if total_pages > 1:
            st.success(f"📄 显示第 **{start_idx + 1} - {end_idx}** 条记录，共 **{len(df)}** 条记录")

    def _show_current_results_advanced(self):
        """显示当前处理结果 """
        st.markdown("### 📋 当前处理结果")

        if not st.session_state.current_results:
            st.info("💡 暂无处理结果")
            return

        # 初始化分页状态
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 0

        # 第一行 使用expander来组织控制面板
        with st.expander("控制选项", expanded=False):
            # 第一行：基本控制
            row1_col1, row1_col2, row1_col3, row1_col4 = st.columns([1, 1, 1, 1])

            with row1_col1:
                # st.write("**📊 每页显示条数：")
                items_per_page = st.selectbox(
                    "选择每页显示数量",
                    [10, 20, 50, 100],
                    index=0,  # 默认选择10条
                    label_visibility="collapsed",  # 隐藏标签
                    key="page_size_inline"
                )

            with row1_col4:
                if st.button("📥 导出全部", type="primary", use_container_width=True):
                    self._export_current_results()

        # 创建数据框
        df = pd.DataFrame(st.session_state.current_results)
        # 调整列顺序
        column_order = ['费用所属月份(审核月份)', '事业部', '大项目', '文件名', '姓名', '发票代码', '发票号码',
                        '开票日期', '金额', '税率', '税额', '价税合计',
                        '状态']
        existing_columns = [col for col in column_order if col in df.columns]
        df = df[existing_columns + [col for col in df.columns if col not in existing_columns]]
        # 分页计算
        total_pages = max(1, (len(df) + items_per_page - 1) // items_per_page)
        # 确保当前页不超出范围
        current_page = st.session_state.current_page
        if current_page >= total_pages:
            st.session_state.current_page = total_pages - 1
            st.rerun()

        st.markdown("#### 📊 数据表格")
        # 第二行：分页导航（行式布局）
        with st.expander("分页导航", expanded=False):
            # 分页信息显示
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.write(f"**第 {current_page + 1} 页，共 {total_pages} 页**")

            # 显示当前页数据
            with col2:
                start_idx = current_page * items_per_page
                end_idx = min((current_page + 1) * items_per_page, len(df))
                st.write(f"**显示记录：{start_idx + 1} - {end_idx}**")

            with col3:
                st.write(f"**总计：{len(df)} 条记录**")

            # 分页按钮行（关键修复：正确的按钮逻辑）
            if total_pages > 1:
                # 使用表单确保按钮点击能触发rerun
                with st.form("pagination_form"):
                    btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns([1, 1, 2, 1, 1])

                    with btn_col1:
                        if st.form_submit_button("⏮️ 首页", use_container_width=True,
                                                 disabled=current_page == 0):
                            st.session_state.current_page = 0
                            st.rerun()

                    with btn_col2:
                        if st.form_submit_button("◀️ 上一页", use_container_width=True,
                                                 disabled=current_page == 0):
                            st.session_state.current_page = max(0, current_page - 1)
                            st.rerun()

                    with btn_col3:
                        # 页码选择器
                        new_page = st.selectbox(
                            "选择页码",
                            options=list(range(1, total_pages + 1)),
                            index=current_page,
                            label_visibility="collapsed",  # 隐藏标签
                            key="page_selector"
                        ) - 1

                        # 检测页码变化
                        if new_page != current_page:
                            st.session_state.current_page = new_page
                            st.rerun()

                    with btn_col4:
                        if st.form_submit_button("▶️ 下一页", use_container_width=True,
                                                 disabled=current_page >= total_pages - 1):
                            st.session_state.current_page = min(total_pages - 1, current_page + 1)
                            st.rerun()

                    with btn_col5:
                        if st.form_submit_button("⏭️ 末页", use_container_width=True,
                                                 disabled=current_page >= total_pages - 1):
                            st.session_state.current_page = total_pages - 1
                            st.rerun()
        st.dataframe(
            df.iloc[start_idx:end_idx],
            use_container_width=True,
            height=min(600, items_per_page * 35)
        )

        # 第三行：统计信息
        st.markdown("#### 📈 处理统计")
        self._show_simple_statistics()

    def _show_simple_statistics(self):
        """显示简化的统计信息"""
        success_count = len([r for r in st.session_state.current_results if r.get('状态') == '成功'])
        total_count = len(st.session_state.current_results)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        # 使用指标卡片行式布局
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("总文件数", total_count)

        with col2:
            st.metric("成功数", success_count)

        with col3:
            st.metric("失败数", total_count - success_count)

        with col4:
            st.metric("成功率", f"{success_rate:.1f}%")

    # def _show_beautiful_statistics(self):
    #     """显示美观的统计信息卡片"""
    #     success_count = len([r for r in st.session_state.current_results if r.get('状态') == '成功'])
    #     total_count = len(st.session_state.current_results)
    #     success_rate = (success_count / total_count * 100) if total_count > 0 else 0
    #
    #     st.markdown("### 📈 处理统计")
    #
    #     col1, col2, col3, col4 = st.columns(4)
    #
    #     with col1:
    #         st.markdown(f"""
    #         <div class="stat-card">
    #             <div style="font-size: 12px; opacity: 0.9;">总文件数</div>
    #             <div style="font-size: 24px; font-weight: bold;">{total_count}</div>
    #             <div style="font-size: 12px;">📁 全部记录</div>
    #         </div>
    #         """, unsafe_allow_html=True)
    #
    #     with col2:
    #         st.markdown(f"""
    #         <div class="stat-card" style="background: linear-gradient(135deg, #00b894 0%, #00a085 100%);">
    #             <div style="font-size: 12px; opacity: 0.9;">成功数</div>
    #             <div style="font-size: 24px; font-weight: bold;">{success_count}</div>
    #             <div style="font-size: 12px;">✅ 处理成功</div>
    #         </div>
    #         """, unsafe_allow_html=True)
    #
    #     with col3:
    #         st.markdown(f"""
    #         <div class="stat-card" style="background: linear-gradient(135deg, #e17055 0%, #d63031 100%);">
    #             <div style="font-size: 12px; opacity: 0.9;">失败数</div>
    #             <div style="font-size: 24px; font-weight: bold;">{total_count - success_count}</div>
    #             <div style="font-size: 12px;">❌ 处理失败</div>
    #         </div>
    #         """, unsafe_allow_html=True)
    #
    #     with col4:
    #         rate_color = "#00b894" if success_rate >= 90 else "#fdcb6e" if success_rate >= 70 else "#e17055"
    #         st.markdown(f"""
    #         <div class="stat-card" style="background: linear-gradient(135deg, {rate_color} 0%, #2d3436 100%);">
    #             <div style="font-size: 12px; opacity: 0.9;">成功率</div>
    #             <div style="font-size: 24px; font-weight: bold;">{success_rate:.1f}%</div>
    #             <div style="font-size: 12px;">📊 处理效率</div>
    #         </div>
    #         """, unsafe_allow_html=True)

    def _show_current_results(self):
        """显示当前处理结果 - 添加清除按钮"""
        st.markdown("### 📋 当前处理结果")

        if not st.session_state.current_results:
            st.info("💡 暂无处理结果")
            return

        # 添加清除按钮在结果区域
        col1, col2 = st.columns([4, 1])
        with col2:
            if st.button("🗑️ 清除当前结果", type="secondary", use_container_width=True):
                self._clear_results()
                st.rerun()

        # 创建数据框 - 确保数据有效性
        try:
            df = pd.DataFrame(st.session_state.current_results)

            # 检查数据完整性
            if df.empty:
                st.warning("⚠️ 结果数据为空")
                return

            # 调整列顺序
            column_order = ['费用所属月份(审核月份)', '事业部', '大项目', '文件名', '姓名', '发票代码', '发票号码',
                            '开票日期', '金额', '税率', '税额', '价税合计',
                            '状态']
            existing_columns = [col for col in column_order if col in df.columns]
            df = df[existing_columns + [col for col in df.columns if col not in existing_columns]]

            # 分页设置
            items_per_page = 20  # 每页显示20条记录
            total_pages = (len(df) + items_per_page - 1) // items_per_page
            # 分页控件
            if total_pages > 1:
                col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
                with col2:
                    page = st.selectbox(
                        "选择页码",
                        range(1, total_pages + 1),
                        format_func=lambda x: f"第 {x} 页（共 {total_pages} 页）",
                        key="result_page"
                    ) - 1
                with col4:
                    st.write(f"**总计：{len(df)} 条记录**")
            else:
                page = 0

            # 计算当前页的数据范围
            start_idx = page * items_per_page
            end_idx = min((page + 1) * items_per_page, len(df))

            # 显示当前页的数据
            st.dataframe(df.iloc[start_idx:end_idx], use_container_width=True, height=600)

            # 显示分页信息
            if total_pages > 1:
                st.info(
                    f"📄 显示第 **{start_idx + 1}** 到 **{end_idx}** 条记录，共 **{len(df)}** 条记录（第 {page + 1}/{total_pages}页）")
            # 显示表格
            # st.dataframe(df, use_container_width=True, height=400)

        except Exception as e:
            st.error(f"❌ 显示结果表格时出错: {str(e)}")
            # 显示原始结果作为备选
            st.json(st.session_state.current_results)

        # 统计信息
        success_count = len([r for r in st.session_state.current_results if r.get('状态') == '成功'])
        total_count = len(st.session_state.current_results)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总文件数", total_count)
        with col2:
            st.metric("成功数", success_count)
        with col3:
            st.metric("失败数", total_count - success_count)
        with col4:
            st.metric("成功率", f"{success_rate:.1f}%")

        # 下载功能
        if st.button("📥 导出当前结果", type="primary"):
            self._export_current_results()

    def _export_current_results(self):
        """导出当前结果"""
        if not st.session_state.current_results:
            st.warning("⚠️ 没有可导出的数据")
            return

        # 构造你想要的列顺序
        desired_column_order = [
            '费用所属月份(审核月份)', '事业部', '大项目', '文件名', '姓名',
            '发票代码', '发票号码', '开票日期', '金额', '税率', '税额',
            '价税合计', '状态'
        ]
        df = pd.DataFrame(st.session_state.current_results)
        # 只保留你想要的列（防止意外字段干扰），并且按照指定顺序排列
        # 如果某些列不存在，可以用 df.get(col, default=None) 或提前过滤
        available_cols = [col for col in desired_column_order if col in df.columns]
        df_export = df[available_cols]
        # 导出到 Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='发票数据')

        excel_data = output.getvalue()
        b64 = base64.b64encode(excel_data).decode()
        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="当前发票提取结果.xlsx">点击下载Excel文件</a>'
        st.markdown(href, unsafe_allow_html=True)

    def _file_upload_section(self):
        """文件上传区域"""
        st.markdown("#### 📤 上传PDF发票文件")

        # 添加上传器key到会话状态（用于重置）
        if 'file_uploader_key' not in st.session_state:
            st.session_state.file_uploader_key = 0

        # 清除按钮
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("**选择PDF文件：**")
        with col2:
            if st.button("🗑️ 一键清除所有文件", type="secondary", use_container_width=True):
                # 通过改变uploader的key来彻底重置
                st.session_state.file_uploader_key += 1
                st.session_state.uploaded_files = []
                st.success("✅ 所有文件已清除")
                st.rerun()

        uploaded_files = st.file_uploader(
            "选择PDF文件",
            type=["pdf"],
            accept_multiple_files=True,
            help="支持多文件上传，最大200MB",
            key=f"file_uploader_{st.session_state.file_uploader_key}",  # 动态key
            label_visibility="collapsed"
        )

        if uploaded_files:
            st.session_state.uploaded_files = uploaded_files
            st.session_state.file_source = "upload"
            st.success(f"✅ 已上传 {len(uploaded_files)} 个文件")

    def _folder_processing_section(self):
        """文件夹处理区域"""
        st.markdown("#### 📂 文件夹处理")
        folder_path = st.text_input(
            "请输入包含PDF文件的文件夹完整路径",
            value=st.session_state.folder_path,
            placeholder="例如：C:/Users/发票文件 或 ./invoices",
            help="请输入包含PDF发票文件的文件夹完整路径",
            label_visibility="collapsed"
        )

        if folder_path:
            st.session_state.folder_path = folder_path
            st.session_state.file_source = "folder"

            if os.path.exists(folder_path):
                pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
                if pdf_files:
                    st.success(f"✅ 找到 {len(pdf_files)} 个PDF文件")
                else:
                    st.warning("⚠️ 文件夹中没有找到PDF文件")
            else:
                st.error("❌ 文件夹路径不存在")

    def _processing_options_section(self):
        """处理选项区域"""
        st.markdown("#### ⚙️ 处理选项")
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        years = list(range(2025, 2031))  # 2025 ~ 2030
        months = [f"{i}月" for i in range(1, 13)]
        with col1:
            # st.checkbox("从文件名提取姓名", value=True, key="extract_name")
            st.selectbox(
                "事业部",
                ["第一事业部", "第二事业部", "第三事业部", "第四事业部", "第五事业部"],
                index=1,
                key="drop"  # 保存到 st.session_state["drop"]
            )

        with col2:
            st.selectbox(
                "大项目",
                ["深圳移动网优代维项目", "河源移动网优代维项目", "梅州移动网优代维项目"],
                key="daxiangmu"
            )

        with col3:
            st.selectbox("选择年份", years, key="sel_year")

        with col4:
            st.selectbox("选择月份", months, key="sel_month")

    def results_page(self):
        """结果查看页面 - 只显示当前处理结果"""
        st.title("📊 处理结果")

        if not st.session_state.current_results:
            st.info("💡 暂无处理结果，请先处理发票文件")
            return

        # 使用新的分页显示方法
        self._show_current_results_advanced()  # 使用高级版本

    def analysis_page(self):
        """数据分析页面"""
        st.title("📈 数据分析")

        if not st.session_state.current_results:
            st.info("📊 没有可分析的数据，请先处理发票文件")
            return

        df = pd.DataFrame(st.session_state.current_results)

        # 总体统计
        st.markdown("### 📊 总体统计")
        success_count = len([r for r in st.session_state.current_results if r.get('状态') == '成功'])
        total_count = len(st.session_state.current_results)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("处理文件数", total_count)
        with col2:
            st.metric("成功数量", success_count)
        with col3:
            st.metric("失败数量", total_count - success_count)
        with col4:
            st.metric("处理成功率", f"{success_rate:.1f}%")

        # 可视化分析
        st.markdown("### 📈 可视化分析")

        tab1, tab2 = st.tabs(["金额分析", "成功率分析"])

        with tab1:
            if '金额' in df.columns:
                amounts = df['金额'].dropna()
                if len(amounts) > 0:
                    fig = px.histogram(
                        amounts,
                        title='金额分布',
                        nbins=20,
                        labels={'value': '金额', 'count': '数量'}
                    )
                    st.plotly_chart(fig, use_container_width=True)

        with tab2:
            # 成功率饼图
            if total_count > 0:
                fig = px.pie(
                    values=[success_count, total_count - success_count],
                    names=['成功', '失败'],
                    title='处理成功率分布',
                    color_discrete_sequence=['#27ae60', '#e74c3c']
                )
                st.plotly_chart(fig, use_container_width=True)

    def system_settings_page(self):
        """系统设置页面"""
        st.title("⚙️ 系统设置")
        st.info("🔧 系统设置功能开发中...")

    def help_page(self):
        """使用帮助页面"""
        st.title("❓ 使用帮助")
        st.info("📚 帮助文档功能开发中...")



    def run(self):
        """运行应用 - 添加Token验证和自动刷新"""

        # 2. 检查Token有效性
        if not st.session_state.get('logged_in'):
            if not self._check_token_validity():
                self.login_page()
                return

        # 3. 显示主界面
        selected = self.create_sidebar()
        # 4、显示主内容区域
        st.markdown("""
        <div class="main-content">
            <h1 class="main-title">智能发票提取系统</h1>
            <p class="subtitle">高效、准确的发票信息自动提取工具</p>
        </div>
        """, unsafe_allow_html=True)

        # 5. 根据选择显示不同内容,# 功能区路由
        if selected == "发票提取":
            self.invoice_extraction_page()
        elif selected == "结果查看":
            self.results_page()
        elif selected == "数据分析":
            self.analysis_page()
        elif selected == "系统设置":
            self.system_settings_page()
        elif selected == "使用帮助":
            self.help_page()
        elif selected == "分类管理":
            self.classification_page()  # 新增分类管理页面


class ClassificationService:
    """分类服务类"""
    pass  # 可以在这里添加与分类相关的辅助方法

if __name__ == "__main__":
    app = FrontendApp()
    app.run()
