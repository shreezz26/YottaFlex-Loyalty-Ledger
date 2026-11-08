
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.database import initialize_database

from app.ledger_engine import (
    accrue_points,
    redeem_points,
    reverse_accrual,
    expire_points,
)

from app.return_engine import process_return

from app.tier_engine import (
    update_customer_tier,
    recalculate_customer_tier,
)

from app.audit import run_all_audits


# ============================================================
# APPLICATION LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="YottaFlex Loyalty Ledger API",
    description=(
        "Loyalty points management, tier progression, "
        "returns, expiry and audit intelligence."
    ),
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================
# REQUEST MODELS
# ============================================================

class AccrualRequest(BaseModel):
    account_id: str
    order_id: str
    net_amount: float = Field(gt=0)
    validity_days: int = Field(default=365, gt=0)


class RedemptionRequest(BaseModel):
    account_id: str
    reward_id: str


class ReversalRequest(BaseModel):
    original_transaction_id: str
    return_amount: float | None = Field(default=None, gt=0)


class ReturnRequest(BaseModel):
    order_id: str
    return_amount: float = Field(gt=0)


class ExpiryRequest(BaseModel):
    as_of: str | None = None


class TierUpdateRequest(BaseModel):
    account_id: str
    qualifying_spend: float = Field(ge=0)


class TierRecalculationRequest(BaseModel):
    account_id: str


# ============================================================
# COMMON OPERATION HANDLER
# ============================================================

def execute_operation(operation, **kwargs):
    try:
        result = operation(**kwargs)

        return {
            "success": True,
            "data": result
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="An internal server error occurred."
        )


# ============================================================
# GENERAL ROUTES
# ============================================================

@app.get("/")
def home():
    return {
        "message": "YottaFlex Loyalty Ledger API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


# ============================================================
# POINTS ACCRUAL
# ============================================================

@app.post("/accrual")
def create_accrual(request: AccrualRequest):

    return execute_operation(
        accrue_points,
        account_id=request.account_id,
        order_id=request.order_id,
        net_amount=request.net_amount,
        validity_days=request.validity_days
    )


# ============================================================
# POINTS REDEMPTION
# ============================================================

@app.post("/redemption")
def create_redemption(request: RedemptionRequest):

    return execute_operation(
        redeem_points,
        account_id=request.account_id,
        reward_id=request.reward_id
    )


# ============================================================
# POINTS REVERSAL
# ============================================================

@app.post("/reversal")
def create_reversal(request: ReversalRequest):

    return execute_operation(
        reverse_accrual,
        original_transaction_id=request.original_transaction_id,
        return_amount=request.return_amount
    )


# ============================================================
# ORDER RETURNS
# ============================================================

@app.post("/returns")
def create_return(request: ReturnRequest):

    return execute_operation(
        process_return,
        order_id=request.order_id,
        return_amount=request.return_amount
    )


# ============================================================
# POINTS EXPIRY
# ============================================================

@app.post("/expiry/run")
def run_expiry(request: ExpiryRequest):

    return execute_operation(
        expire_points,
        as_of=request.as_of
    )


# ============================================================
# TIER MANAGEMENT
# ============================================================

@app.post("/tier/update")
def update_tier(request: TierUpdateRequest):

    return execute_operation(
        update_customer_tier,
        account_id=request.account_id,
        qualifying_spend=request.qualifying_spend
    )


@app.post("/tier/recalculate")
def recalculate_tier(request: TierRecalculationRequest):

    return execute_operation(
        recalculate_customer_tier,
        account_id=request.account_id
    )


# ============================================================
# AUDIT INTELLIGENCE
# ============================================================

@app.get("/audit")
def get_audit_results():

    try:
        results = run_all_audits()

        return {
            "success": True,
            "message": "Audit checks completed.",
            "results": results
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Audit execution failed."
        )
