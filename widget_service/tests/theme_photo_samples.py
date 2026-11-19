"""仅供测试的构图，不向运行注册表添加已删除的图片。"""

from services.post_layout_theme_registry import registered_themes


def protected_photo():
    photo = next(item for item in registered_themes("photos")
                 if item.get("id") == "photo-ux-mountain-sunset-lake-square")
    photo["id"] = "test-protected-weather"
    photo.pop("contentEligibility", None)
    return photo
