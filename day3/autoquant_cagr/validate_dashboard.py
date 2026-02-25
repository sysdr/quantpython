#!/usr/bin/env python3
"""
Validation script to verify dashboard displays all metrics correctly.
"""
import sys
import numpy as np
from src.cagr import build_cagr_surface
from src.data_feed import generate_synthetic_prices
from src.dashboard import render_surface_table
from src.config import TENOR_ORDER

def validate_dashboard():
    """Validate that dashboard can render all metrics for all symbols."""
    print("Validating dashboard metrics...")
    
    # Generate test data for all demo symbols
    symbols = ["SPY", "QQQ", "IWM", "GLD", "TLT"]
    surfaces = []
    
    for symbol in symbols:
        rng = hash(symbol) % 1000
        prices = generate_synthetic_prices(
            n_days=1260,
            annual_return=0.08 + (rng % 10) * 0.01,
            annual_vol=0.15 + (rng % 8) * 0.01,
            seed=rng,
        )
        surf = build_cagr_surface(symbol, prices)
        surfaces.append(surf)
    
    # Validate each surface has all required metrics
    all_tenors_present = True
    all_values_finite = True
    all_nan_ratios_valid = True
    
    for surf in surfaces:
        # Check all tenors are present
        for tenor in TENOR_ORDER:
            if tenor not in surf.cagr_by_tenor:
                print(f"❌ {surf.symbol}: Missing tenor {tenor}")
                all_tenors_present = False
        
        # Check at least some values are finite (not all NaN)
        finite_count = sum(1 for t in TENOR_ORDER 
                          if np.isfinite(surf.cagr_by_tenor.get(t, float("nan"))))
        if finite_count == 0:
            print(f"❌ {surf.symbol}: No finite CAGR values")
            all_values_finite = False
        
        # Check NaN ratio is valid
        if not (0 <= surf.nan_ratio <= 1):
            print(f"❌ {surf.symbol}: Invalid NaN ratio {surf.nan_ratio}")
            all_nan_ratios_valid = False
    
    # Test dashboard rendering
    try:
        table = render_surface_table(surfaces)
        print("✅ Dashboard table rendering: OK")
    except Exception as e:
        print(f"❌ Dashboard table rendering failed: {e}")
        return False
    
    # Summary
    if all_tenors_present and all_values_finite and all_nan_ratios_valid:
        print("\n✅ All dashboard metrics validated successfully!")
        print(f"   - {len(surfaces)} symbols processed")
        print(f"   - {len(TENOR_ORDER)} tenors per symbol")
        print(f"   - All surfaces have valid metrics")
        return True
    else:
        print("\n❌ Dashboard validation failed")
        return False

if __name__ == "__main__":
    success = validate_dashboard()
    sys.exit(0 if success else 1)

