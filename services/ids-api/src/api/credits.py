
"""
LLM Credit Management API
=========================

Endpoints for checking credit balance, cost estimates, and provider health.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
from datetime import datetime

# Import CreditChecker from the parent directory (src)
# Since this file is in src/api/credits.py, we might need to adjust path or import if llm_credit_checker is in src/
# Assuming llm_credit_checker is in src/, and this file is loaded as api.credits
# The main.py adds src/ to sys.path, so "import llm_credit_checker" should work if run from src context.
# However, if using relative imports: "from ..llm_credit_checker import CreditChecker"

from llm_credit_checker import CreditChecker

credits_router = APIRouter(prefix="/api/llm/credits", tags=["LLM Credits"])

_checker = None

def get_credit_checker():
    global _checker
    if _checker is None:
        _checker = CreditChecker()
    return _checker

@credits_router.get("/", response_model=Dict[str, Any])
async def get_all_credits(checker: CreditChecker = Depends(get_credit_checker)):
    """
    Get credit status for all configured providers.
    Returns cached results if recent, otherwise refreshes.
    """
    try:
        status = await checker.check_all_providers()
        # Serialize CreditInfo objects to plain dicts for JSON response
        return {name: (info.to_dict() if hasattr(info, 'to_dict') else info)
                for name, info in status.items()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check credits: {str(e)}")

@credits_router.get("/{provider}", response_model=Dict[str, Any])
async def get_provider_credit(
    provider: str, 
    force_refresh: bool = False,
    checker: CreditChecker = Depends(get_credit_checker)
):
    """
    Get credit status for a specific provider.
    """
    try:
        status = await checker.check_provider(provider, force_refresh=force_refresh)
        if not status:
            raise HTTPException(status_code=404, detail=f"Provider {provider} not found or not configured")
        return status
    except ValueError as e:
         raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check provider: {str(e)}")
