from apply_patch.updater.crypto_utils import (
    generate_keypair,
    sign_data,
    verify_signature,
)


def test_keypair_generation_length():
    """Kiểm tra độ dài chuẩn của khóa Ed25519 (32 bytes)."""
    priv, pub = generate_keypair()
    assert len(priv) == 32
    assert len(pub) == 32


def test_sign_and_verify_success():
    """Luồng chuẩn: Ký và xác thực thành công."""
    priv, pub = generate_keypair()
    data = b'{"version": "1.0.1", "url": "https://server/patch.bin"}'
    signature = sign_data(priv, data)
    
    # Chữ ký Ed25519 luôn có độ dài 64 bytes
    assert len(signature) == 64 
    assert verify_signature(pub, signature, data) is True


def test_verify_fails_with_tampered_data():
    """Bảo mật: Dữ liệu bị giả mạo (Man-in-the-Middle) phải bị từ chối."""
    priv, pub = generate_keypair()
    original_data = b'{"version": "1.0.1", "url": "https://server/patch.bin"}'
    signature = sign_data(priv, original_data)
    
    tampered_data = b'{"version": "1.0.1", "url": "https://hacker/malware.bin"}'
    assert verify_signature(pub, signature, tampered_data) is False


def test_verify_fails_with_wrong_key():
    """Bảo mật: Chữ ký hợp lệ nhưng xác thực bằng Public Key khác phải thất bại."""
    priv1, _pub1 = generate_keypair()
    _, pub2 = generate_keypair()
    
    data = b"secure manifest payload"
    signature = sign_data(priv1, data)
    
    assert verify_signature(pub2, signature, data) is False


def test_verify_handles_corrupted_signature():
    """Defense in Depth: App không crash khi nhận được chữ ký rác / sai độ dài."""
    _, pub = generate_keypair()
    data = b"some data"
    
    # Chữ ký giả mạo, không đúng cấu trúc
    corrupted_signature_64 = b"0" * 64 
    corrupted_signature_short = b"invalid"
    
    assert verify_signature(pub, corrupted_signature_64, data) is False
    assert verify_signature(pub, corrupted_signature_short, data) is False


def test_verify_handles_invalid_key_length():
    """Defense in Depth: App không crash khi Public Key bị lỗi."""
    data = b"some data"
    signature = b"0" * 64
    
    # Public key quá ngắn hoặc quá dài
    assert verify_signature(b"short_key", signature, data) is False
    assert verify_signature(b"0" * 64, signature, data) is False