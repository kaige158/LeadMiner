@echo off
chcp 65001 >nul
echo ========================================
echo   文人·外贸客户号码查找工具 - 打包为 EXE
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 安装依赖
echo [1/3] 安装依赖...
pip install -r requirements.txt customtkinter pyinstaller -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM 打包
echo [2/3] 开始打包...
pyinstaller --onefile --windowed --name "文人·客户查找工具" --clean --noconfirm --add-data "number_finder.py;." --add-data "api_guide.html;." number_finder_gui.py

if %errorlevel% neq 0 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

REM 完成
echo [3/3] 打包完成！
echo.
echo 可执行文件位于: dist\文人·客户查找工具.exe
echo 将该文件发送给他人即可直接使用（无需安装Python）。
echo.

pause
