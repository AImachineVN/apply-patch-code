; Inno Setup Script for Apply Patch Tool
; Enterprise Installer Configuration

[Setup]
; Metadata thương mại (Hiển thị trong Control Panel > Programs and Features)
AppId={{A1B2C3D4-E5F6-7890-1234-567890ABCDEF}
AppName=Apply Patch Code
AppVersion=1.0.0
AppVerName=Apply Patch Code v1.0
AppPublisher=ApplyPatchCode
AppPublisherURL=https://yourcompany.com
AppSupportURL=https://yourcompany.com/support
SetupIconFile=assets\logo.ico

; Cấu trúc thư mục cài đặt chuẩn Enterprise
DefaultDirName={autopf}\ApplyPatchCode
DefaultGroupName=Apply Patch Code
AllowNoIcons=yes

; Yêu cầu quyền Admin để ghi vào Program Files (Hỗ trợ Auto-Updater ghi đè sau này)
PrivilegesRequired=admin

; Cấu hình file Output
OutputDir=release
OutputBaseFilename=ApplyPatchCode_Setup_v1.0.0

; Thuật toán nén mạnh nhất của Inno Setup để giảm dung lượng file Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Ngăn chặn việc cài đặt nhiều phiên bản song song gây xung đột
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Nếu máy bạn có file ngôn ngữ tiếng Việt (Vietnamese.isl), hãy bỏ comment dòng dưới
; Name: "vietnamese"; MessagesFile: "compiler:Languages\Vietnamese.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"
Name: "launchapp"; Description: "Launch application after installation"; GroupDescription: "Additional options:"; Flags: unchecked

[Files]
; Copy file .exe đã build từ Nuitka vào thư mục cài đặt
; Cờ 'ignoreversion' đảm bảo bản cập nhật sau luôn ghi đè bản cũ nếu có
Source: "dist\ApplyPatchCode.exe"; DestDir: "{app}"; Flags: ignoreversion

; Copy shortcut icon để Start Menu + Desktop shortcut dùng logo riêng
Source: "assets\logo_shortcut.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

; Nếu bạn có file License Agreement (EULA), hãy bỏ comment dòng dưới

[Icons]
; Tạo Shortcut trong Start Menu (dùng logo_shortcut.ico)
Name: "{group}\Apply Patch Tool"; Filename: "{app}\ApplyPatchCode.exe"; IconFilename: "{app}\assets\logo_shortcut.ico"
Name: "{group}\Uninstall Apply Patch Tool"; Filename: "{uninstallexe}"

; Tạo Shortcut ngoài Desktop (nếu user tick chọn) - dùng logo_shortcut.ico
Name: "{commondesktop}\Apply Patch Tool"; Filename: "{app}\ApplyPatchCode.exe"; IconFilename: "{app}\assets\logo_shortcut.ico"; Tasks: desktopicon

[Run]
; Tùy chọn tự động mở App ngay sau khi bấm Finish
Filename: "{app}\ApplyPatchCode.exe"; Description: "Launch Apply Patch Tool"; Flags: nowait postinstall skipifsilent; Tasks: launchapp

[UninstallDelete]
; Defense in Depth: Dọn dẹp các file rác (như file log, file patch .tmp)
; có thể sinh ra trong quá trình App hoạt động mà Nuitka không lường trước được.
Type: files; Name: "{app}\*.tmp"
Type: files; Name: "{app}\*.log"

; LƯU Ý: Chúng ta KHÔNG xóa thư mục %APPDATA%\ApplyPatchTool
; để bảo vệ an toàn cho các bản Backup và dữ liệu người dùng.