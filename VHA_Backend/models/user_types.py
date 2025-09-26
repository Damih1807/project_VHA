from enum import Enum
from typing import Dict, Any, Optional

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    MODERATOR = "MODERATOR"

class UserPermissions(Dict[str, Any]):
    """Permissions được lưu trữ dưới dạng JSON object"""
    pass

class UserInfo:
    def __init__(
        self,
        id: str,
        email: str,
        full_name: str,
        username: str,
        role: UserRole,
        permissions: UserPermissions,
        created_at: str,
        is_active: bool
    ):
        self.id = id
        self.email = email
        self.full_name = full_name
        self.username = username
        self.role = role
        self.permissions = permissions
        self.created_at = created_at
        self.is_active = is_active

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "username": self.username,
            "role": self.role.value,
            "permissions": self.permissions,
            "created_at": self.created_at,
            "is_active": self.is_active
        }

def get_user_role(role_string: str) -> UserRole:
    """Convert string role thành UserRole enum"""
    try:
        return UserRole(role_string.upper())
    except ValueError:
        return UserRole.MEMBER

def is_valid_role(role_string: str) -> bool:
    """Kiểm tra xem role có hợp lệ không"""
    try:
        UserRole(role_string.upper())
        return True
    except ValueError:
        return False

DEFAULT_PERMISSIONS = {
    UserRole.ADMIN: {
        "manage_users": True,
        "manage_files": True,
        "view_logs": True,
        "system_config": True,
        "access_admin_panel": True
    },
    UserRole.MODERATOR: {
        "manage_users": False,
        "manage_files": True,
        "view_logs": True,
        "system_config": False,
        "access_admin_panel": True
    },
    UserRole.MEMBER: {
        "manage_users": False,
        "manage_files": False,
        "view_logs": False,
        "system_config": False,
        "access_admin_panel": False
    }
}

def get_default_permissions(role: UserRole) -> UserPermissions:
    """Lấy default permissions cho role"""
    return DEFAULT_PERMISSIONS.get(role, DEFAULT_PERMISSIONS[UserRole.MEMBER])

def validate_and_merge_permissions(role: UserRole, custom_permissions: dict = None) -> UserPermissions:
    """
    Validate và merge custom permissions với default permissions cho role
    
    Args:
        role: UserRole của user
        custom_permissions: Custom permissions được truyền vào (có thể None)
    
    Returns:
        UserPermissions: Permissions đã được merge và validate
    """
    default_perms = get_default_permissions(role)
    
    if not custom_permissions:
        return default_perms.copy()
    
    # Merge custom permissions với default, ưu tiên custom permissions
    merged_permissions = default_perms.copy()
    merged_permissions.update(custom_permissions)
    
    # Đảm bảo tất cả các trường permission đều có mặt
    for perm_key in default_perms.keys():
        if perm_key not in merged_permissions:
            merged_permissions[perm_key] = default_perms[perm_key]
    
    return merged_permissions

def validate_permission_structure(permissions: dict) -> tuple[bool, str]:
    """
    Validate cấu trúc của permissions object
    
    Args:
        permissions: Dictionary chứa permissions
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(permissions, dict):
        return False, "Permissions must be a dictionary"
    
    expected_permissions = {
        "manage_users", "manage_files", "view_logs", 
        "system_config", "access_admin_panel"
    }
    
    # Kiểm tra các trường bắt buộc
    for perm in expected_permissions:
        if perm not in permissions:
            return False, f"Missing required permission: {perm}"
        
        if not isinstance(permissions[perm], bool):
            return False, f"Permission '{perm}' must be a boolean value"
    
    # Kiểm tra các trường không mong muốn
    for perm in permissions.keys():
        if perm not in expected_permissions:
            return False, f"Unknown permission: {perm}"
    
    return True, "Valid permission structure"
