"""Caddy reverse proxy routes for BoneIO Web UI (SSL/TLS certificate management)."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/caddy", tags=["caddy"])

# Default paths - can be overridden via environment variables
CADDY_CONFIG_DIR = os.environ.get("CADDY_CONFIG_DIR", "/opt/boneio/docker/nodered/caddy")
CADDYFILE_PATH = os.path.join(CADDY_CONFIG_DIR, "Caddyfile")
CADDY_DATA_DIR = os.path.join(CADDY_CONFIG_DIR, "data")


class CaddyConfig(BaseModel):
    """Caddy configuration model."""
    
    mode: str = Field(
        default="self_signed",
        description="Certificate mode: 'self_signed' or 'acme'"
    )
    domain: Optional[str] = Field(
        default=None,
        description="Domain name for ACME certificate (required when mode is 'acme')"
    )
    email: Optional[str] = Field(
        default=None,
        description="Email for ACME registration (optional but recommended)"
    )
    
    class Config:
        """Pydantic config."""
        
        json_schema_extra = {
            "example": {
                "mode": "acme",
                "domain": "boneio.example.com",
                "email": "admin@example.com"
            }
        }


class CertificateInfo(BaseModel):
    """Certificate information model."""
    
    mode: str
    domain: Optional[str] = None
    email: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    issuer: Optional[str] = None
    is_self_signed: bool = True


class CaddyStatus(BaseModel):
    """Caddy status response model."""
    
    status: str
    config: CaddyConfig
    certificate: Optional[CertificateInfo] = None
    message: Optional[str] = None


def parse_caddyfile() -> CaddyConfig:
    """
    Parse current Caddyfile and extract configuration.
    
    Returns:
        CaddyConfig with current settings.
    """
    config = CaddyConfig()
    
    if not os.path.exists(CADDYFILE_PATH):
        _LOGGER.warning("Caddyfile not found at %s", CADDYFILE_PATH)
        return config
    
    try:
        with open(CADDYFILE_PATH, "r") as f:
            content = f.read()
        
        # Check if using internal (self-signed) TLS
        if "tls internal" in content:
            config.mode = "self_signed"
        else:
            config.mode = "acme"
        
        # Extract domain from server block (e.g., "example.com {" or "example.com:443 {")
        domain_match = re.search(r"^([a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})\s*(?::\d+)?\s*\{", content, re.MULTILINE)
        if domain_match:
            config.domain = domain_match.group(1)
        
        # Extract email from tls directive
        email_match = re.search(r"tls\s+([^\s]+@[^\s]+)", content)
        if email_match:
            config.email = email_match.group(1)
        
    except Exception as e:
        _LOGGER.error("Error parsing Caddyfile: %s", e)
    
    return config


def generate_caddyfile(config: CaddyConfig) -> str:
    """
    Generate Caddyfile content based on configuration.
    
    Args:
        config: CaddyConfig with desired settings.
        
    Returns:
        Caddyfile content as string.
    """
    # Global options
    lines = [
        "{",
        "\t# Global options",
    ]
    
    if config.mode == "self_signed":
        lines.append("\tauto_https off")
    
    lines.extend([
        "\tadmin off",
        "}",
        "",
    ])
    
    # HTTP redirect (only for ACME mode)
    if config.mode == "acme" and config.domain:
        lines.extend([
            ":80 {",
            f"\tredir https://{config.domain}{{uri}} permanent",
            "}",
            "",
        ])
    elif config.mode == "self_signed":
        lines.extend([
            ":80 {",
            "\tredir https://{host}{uri} permanent",
            "}",
            "",
        ])
    
    # HTTPS server block
    if config.mode == "acme" and config.domain:
        lines.append(f"{config.domain} {{")
        if config.email:
            lines.append(f"\ttls {config.email}")
        else:
            lines.append("\ttls")
    else:
        lines.extend([
            ":443 {",
            "\t# Self-signed certificate on startup",
            "\ttls internal",
        ])
    
    # Common configuration
    lines.extend([
        "",
        "\t# Handle errors (502, 503, 504)",
        "\thandle_errors {",
        "\t\t@502-504 expression {err.status_code} >= 502 && {err.status_code} <= 504",
        "\t\thandle @502-504 {",
        "\t\t\troot * /srv",
        "\t\t\trewrite * /502.html",
        "\t\t\tfile_server",
        "\t\t}",
        "\t}",
        "",
        "\t# Node-RED status endpoint",
        "\thandle /nodered-status {",
        "\t\theader Content-Type application/json",
        '\t\theader X-NodeRed-Available "true"',
        '\t\theader Access-Control-Expose-Headers "X-NodeRed-Available"',
        '\t\trespond `{"available": true}` 200',
        "\t}",
        "",
        "\t# Node-RED reverse proxy",
        "\thandle /nodered/* {",
        "\t\treverse_proxy node-red:1880 {",
        "\t\t\theader_up X-Forwarded-Proto {scheme}",
        '\t\t\theader_down X-NodeRed-Available "true"',
        "\t\t}",
        "\t}",
        "",
        "\t# BoneIO reverse proxy (default)",
        "\thandle {",
        "\t\treverse_proxy host.docker.internal:8090 {",
        "\t\t\theader_up X-Forwarded-Proto {scheme}",
        "\t\t}",
        "\t}",
        "}",
    ])
    
    return "\n".join(lines)


def reload_caddy() -> tuple[bool, str]:
    """
    Reload Caddy configuration.
    
    Returns:
        Tuple of (success, message).
    """
    try:
        # Try docker compose reload first
        result = subprocess.run(
            ["docker", "compose", "exec", "caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
            cwd=CADDY_CONFIG_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True, "Caddy configuration reloaded successfully"
        else:
            # If reload fails, try restart
            result = subprocess.run(
                ["docker", "compose", "restart", "caddy"],
                cwd=CADDY_CONFIG_DIR,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, "Caddy container restarted successfully"
            else:
                return False, f"Failed to reload Caddy: {result.stderr}"
                
    except subprocess.TimeoutExpired:
        return False, "Timeout while reloading Caddy"
    except FileNotFoundError:
        return False, "Docker or docker-compose not found"
    except Exception as e:
        return False, f"Error reloading Caddy: {str(e)}"


@router.get("/config", response_model=CaddyStatus)
async def get_caddy_config():
    """
    Get current Caddy configuration and certificate status.
    
    Returns:
        CaddyStatus with current configuration.
    """
    try:
        config = parse_caddyfile()
        
        cert_info = CertificateInfo(
            mode=config.mode,
            domain=config.domain,
            email=config.email,
            is_self_signed=(config.mode == "self_signed")
        )
        
        # Try to get certificate info from Caddy data directory
        if config.mode == "acme" and config.domain:
            cert_path = os.path.join(
                CADDY_DATA_DIR, 
                "caddy", 
                "certificates", 
                "acme-v02.api.letsencrypt.org-directory",
                config.domain,
                f"{config.domain}.crt"
            )
            
            if os.path.exists(cert_path):
                try:
                    result = subprocess.run(
                        ["openssl", "x509", "-in", cert_path, "-noout", "-dates", "-issuer"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if result.returncode == 0:
                        output = result.stdout
                        
                        # Parse dates
                        not_before = re.search(r"notBefore=(.+)", output)
                        not_after = re.search(r"notAfter=(.+)", output)
                        issuer = re.search(r"issuer=(.+)", output)
                        
                        if not_before:
                            cert_info.valid_from = not_before.group(1).strip()
                        if not_after:
                            cert_info.valid_until = not_after.group(1).strip()
                        if issuer:
                            cert_info.issuer = issuer.group(1).strip()
                        
                        cert_info.is_self_signed = False
                        
                except Exception as e:
                    _LOGGER.warning("Could not read certificate info: %s", e)
        
        return CaddyStatus(
            status="success",
            config=config,
            certificate=cert_info
        )
        
    except Exception as e:
        _LOGGER.error("Error getting Caddy config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config", response_model=CaddyStatus)
async def update_caddy_config(config: CaddyConfig):
    """
    Update Caddy configuration.
    
    Args:
        config: New Caddy configuration.
        
    Returns:
        CaddyStatus with updated configuration.
    """
    try:
        # Validate configuration
        if config.mode == "acme":
            if not config.domain:
                raise HTTPException(
                    status_code=400, 
                    detail="Domain is required for ACME mode"
                )
            
            # Basic domain validation
            if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$", config.domain):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid domain format"
                )
            
            # Basic email validation (if provided)
            if config.email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", config.email):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid email format"
                )
        
        # Generate new Caddyfile
        caddyfile_content = generate_caddyfile(config)
        
        # Backup current Caddyfile
        if os.path.exists(CADDYFILE_PATH):
            backup_path = f"{CADDYFILE_PATH}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                with open(CADDYFILE_PATH, "r") as f:
                    backup_content = f.read()
                with open(backup_path, "w") as f:
                    f.write(backup_content)
                _LOGGER.info("Backed up Caddyfile to %s", backup_path)
            except Exception as e:
                _LOGGER.warning("Could not backup Caddyfile: %s", e)
        
        # Write new Caddyfile
        with open(CADDYFILE_PATH, "w") as f:
            f.write(caddyfile_content)
        
        _LOGGER.info("Updated Caddyfile with mode=%s, domain=%s", config.mode, config.domain)
        
        # Reload Caddy
        success, message = reload_caddy()
        
        if not success:
            _LOGGER.warning("Caddy reload failed: %s", message)
            # Don't fail the request, just warn
            return CaddyStatus(
                status="warning",
                config=config,
                message=f"Configuration saved but reload failed: {message}. Please restart Caddy manually."
            )
        
        return CaddyStatus(
            status="success",
            config=config,
            message="Configuration updated and Caddy reloaded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        _LOGGER.error("Error updating Caddy config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_caddy_config():
    """
    Reload Caddy configuration without changing it.
    
    Returns:
        Status response.
    """
    success, message = reload_caddy()
    
    if success:
        return {"status": "success", "message": message}
    else:
        raise HTTPException(status_code=500, detail=message)


@router.get("/test")
async def test_caddy_connection():
    """
    Test if Caddy is running and accessible.
    
    Returns:
        Status response.
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json", "caddy"],
            cwd=CADDY_CONFIG_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                container_info = json.loads(result.stdout)
                if isinstance(container_info, list):
                    container_info = container_info[0] if container_info else {}
                
                state = container_info.get("State", "unknown")
                
                if state == "running":
                    return {
                        "status": "success",
                        "running": True,
                        "message": "Caddy is running"
                    }
                else:
                    return {
                        "status": "warning",
                        "running": False,
                        "message": f"Caddy container state: {state}"
                    }
            except json.JSONDecodeError:
                # Fallback for older docker compose versions
                if "running" in result.stdout.lower() or "Up" in result.stdout:
                    return {
                        "status": "success",
                        "running": True,
                        "message": "Caddy is running"
                    }
        
        return {
            "status": "error",
            "running": False,
            "message": "Caddy container not found or not running"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "running": False,
            "message": str(e)
        }
