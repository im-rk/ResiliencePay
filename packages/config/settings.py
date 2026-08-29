class Settings:
    fault_injection_enabled: bool = False
    fault_injection_rate: float = 0.0

    # Gate Settings
    gate_max_attempts: int = 3
    gate_min_cool_off_hours: int = 24
    gate_allowed_hour_start: int = 9
    gate_allowed_hour_end: int = 20

settings = Settings()
