from enum import StrEnum


class TenantRoutingMode(StrEnum):
    SUBFOLDER = "SUBFOLDER"
    DOMAIN = "DOMAIN"
