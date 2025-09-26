import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # Discord
    bot_token: str
    channel_id: int

    # OCR & detection
    ocr_confidence_threshold: float = 0.35
    use_easyocr: bool = False
    use_yolo_detection: bool = False
    yolo_model_path: str = "data/models/yolov8n.pt"

    # Advanced OCR controls
    multipass_enabled: bool = True
    low_confidence_retry_threshold: float = 0.25
    region_min_confidence: float = 0.3

    # Router
    router_enable_normalization: bool = True
    router_sportsbook_hints: List[str] = field(default_factory=lambda: ["FanDuel", "DraftKings", "Caesars", "BetMGM"])

    # HTTP
    http_timeout: float = 10.0

    # Update cadences
    scores_update_interval_sec: int = 60
    props_update_interval_sec: int = 20
    settlement_check_interval_sec: int = 60
    catalog_refresh_interval_min: int = 1440

    # Training
    enable_training: bool = True
    training_dataset_dir: str = "data/training/"
    model_output_dir: str = "data/models/"
    retrain_interval_min: int = 720

    # Debug
    debug_logging: bool = True

    # Soccer competitions
    soccer_competitions: List[str] = field(default_factory=lambda: [
        "ENG.1", "ESP.1", "ITA.1", "GER.1", "FRA.1", "MLS"
    ])

    @classmethod
    def from_env(cls) -> "Config":
        token = os.environ.get("BOT_TOKEN", "")
        channel_id = int(os.environ.get("CHANNEL_ID", "0"))
        return cls(
            bot_token=token,
            channel_id=channel_id,
            ocr_confidence_threshold=float(os.environ.get("OCR_CONF", "0.35")),
            use_easyocr=os.environ.get("USE_EASYOCR", "false").lower() == "true",
            use_yolo_detection=os.environ.get("USE_YOLO", "false").lower() == "true",
            yolo_model_path=os.environ.get("YOLO_MODEL", "data/models/yolov8n.pt"),
            multipass_enabled=os.environ.get("MULTIPASS", "true").lower() == "true",
            low_confidence_retry_threshold=float(os.environ.get("LOW_CONF_RETRY", "0.25")),
            region_min_confidence=float(os.environ.get("REGION_MIN_CONF", "0.3")),
            router_enable_normalization=os.environ.get("ROUTER_NORMALIZE", "true").lower() == "true",
            http_timeout=float(os.environ.get("HTTP_TIMEOUT", "10")),
            scores_update_interval_sec=int(os.environ.get("SCORES_INTERVAL", "60")),
            props_update_interval_sec=int(os.environ.get("PROPS_INTERVAL", "20")),
            settlement_check_interval_sec=int(os.environ.get("SETTLEMENT_INTERVAL", "60")),
            catalog_refresh_interval_min=int(os.environ.get("CATALOG_REFRESH_MIN", "1440")),
            enable_training=os.environ.get("ENABLE_TRAINING", "true").lower() == "true",
            training_dataset_dir=os.environ.get("TRAIN_DATA_DIR", "data/training/"),
            model_output_dir=os.environ.get("MODEL_OUT_DIR", "data/models/"),
            retrain_interval_min=int(os.environ.get("RETRAIN_MIN", "720")),
            debug_logging=os.environ.get("DEBUG_LOGGING", "true").lower() == "true",
        )
