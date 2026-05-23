import pytest
from django.conf import settings
from django.contrib.auth.models import User
from linkedin.crypto import encrypt_value, decrypt_value, is_encrypted
from linkedin.models import LinkedInProfile

def test_encryption_decryption_cycle():
    plain = "my-secret-password-123!"
    enc = encrypt_value(plain)
    
    assert enc != plain
    assert is_encrypted(enc) is True
    assert is_encrypted(plain) is False
    
    dec = decrypt_value(enc)
    assert dec == plain

def test_decryption_fallback_for_plaintext():
    plain = "already-plaintext-value"
    dec = decrypt_value(plain)
    assert dec == plain

def test_empty_values():
    assert encrypt_value("") == ""
    assert decrypt_value("") == ""
    assert encrypt_value(None) == ""
    assert decrypt_value(None) == ""

@pytest.mark.django_db
def test_encrypted_char_field_in_database():
    user = User.objects.create(username="cryptotest")
    
    profile = LinkedInProfile.objects.create(
        user=user,
        linkedin_username="crypto@example.com",
        linkedin_password="plain-text-pwd"
    )
    
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT linkedin_password FROM linkedin_linkedinprofile WHERE user_id = %s", [user.id])
        raw_db_value = cursor.fetchone()[0]
        
    assert raw_db_value != "plain-text-pwd"
    assert raw_db_value.startswith("gAAAA")
    
    db_profile = LinkedInProfile.objects.get(id=profile.id)
    assert db_profile.linkedin_password == "plain-text-pwd"
