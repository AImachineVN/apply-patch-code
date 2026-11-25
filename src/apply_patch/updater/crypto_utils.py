from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def generate_keypair() -> tuple[bytes, bytes]:
    """
    Tạo cặp khóa Ed25519 (Private Key, Public Key).
    
    Returns:
        tuple[bytes, bytes]: (private_key_bytes, public_key_bytes)
        Mỗi khóa có độ dài 32 bytes, phù hợp để hardcode hoặc lưu trữ an toàn.
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Serialize to raw bytes (32 bytes each)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    return private_bytes, public_bytes


def sign_data(private_key_bytes: bytes, data: bytes) -> bytes:
    """
    Ký lên dữ liệu bằng Private Key (Dành cho Dev Tool / CI-CD Pipeline).
    
    Args:
        private_key_bytes: 32 bytes của Private Key.
        data: Dữ liệu cần ký (thường là SHA-256 hash của file hoặc nội dung manifest).
        
    Returns:
        bytes: Chữ ký số (64 bytes).
    """
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature = private_key.sign(data)
    return signature


def verify_signature(public_key_bytes: bytes, signature: bytes, data: bytes) -> bool:
    """
    Xác thực chữ ký của dữ liệu bằng Public Key (Dành cho App Host).
    
    Defense in Depth: Hàm này catch mọi exception (InvalidSignature, ValueError, TypeError)
    để đảm bảo App Host không bao giờ bị crash khi nhận được gói patch độc hại 
    hoặc bị lỗi đường truyền gây sai lệch bytes.
    
    Args:
        public_key_bytes: 32 bytes của Public Key (được hardcode trong App).
        signature: 64 bytes chữ ký số đi kèm gói tải xuống.
        data: Dữ liệu gốc cần đối chiếu.
        
    Returns:
        bool: True nếu chữ ký hợp lệ, False nếu không hợp lệ hoặc có bất kỳ lỗi nào.
    """
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, data)
        return True
    except (InvalidSignature, ValueError, TypeError, Exception):
        # Bất kỳ sai lệch nào về độ dài key, format, hay chữ ký không khớp 
        # đều được coi là giả mạo (Tampered) và trả về False.
        return False