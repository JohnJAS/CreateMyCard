"""在启动时选择部署环境提供的卡片工具实现。"""
from importlib.util import find_spec

if find_spec("utils.genui_runtime") is None:
    from utils.card_mock.base_utils import sts_config
    from utils.card_mock.ops_metrics import report_ops_metrics
    from utils.card_mock.upload_file_obs import UploadFileOSMS
else:
    from utils.genui_runtime import UploadFileOSMS, report_ops_metrics, sts_config

__all__ = ["UploadFileOSMS", "report_ops_metrics", "sts_config"]
