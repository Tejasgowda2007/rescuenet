"""
Styles and CSS design tokens for the RescueNet Disaster Operations Center Dashboard.
Provides high-contrast dark operations-center theme by default, with light-mode support,
accessible badges, semantic status pills, station cards, and responsive layouts.
"""

from __future__ import annotations


def get_css(theme: str = "dark") -> str:
    """
    Return comprehensive custom CSS for Streamlit dashboard.
    Always pairs color with clear icons and text labels (WCAG AA compliant).
    """
    is_dark = (theme == "dark")

    bg_main = "#0B0F19" if is_dark else "#F8FAFC"
    bg_surface = "#111827" if is_dark else "#FFFFFF"
    bg_surface_alt = "#1A2234" if is_dark else "#F1F5F9"
    border_color = "#334155" if is_dark else "#CBD5E1"
    border_subtle = "#1E293B" if is_dark else "#E2E8F0"
    text_main = "#F8FAFC" if is_dark else "#0F172A"
    text_muted = "#94A3B8" if is_dark else "#64748B"
    text_accent = "#38BDF8" if is_dark else "#0284C7"

    return f"""
<style>
/* Base Theme & Layout Reset */
html, body, [data-testid="stAppViewContainer"] {{
    background-color: {bg_main} !important;
    color: {text_main} !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}}

/* Top container breathing room */
.block-container {{
    padding-top: 1.2rem !important;
    padding-bottom: 2.5rem !important;
    max-width: 1400px !important;
}}

/* Header Bar */
.rn-header {{
    background: {'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)' if is_dark else 'linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%)'};
    border: 1px solid {border_color};
    border-radius: 12px;
    padding: 18px 24px;
    margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}}

.rn-header-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
}}

.rn-title-group {{
    flex: 1;
    min-width: 320px;
}}

.rn-title {{
    font-size: 1.75rem;
    font-weight: 800;
    color: #FFFFFF;
    letter-spacing: -0.02em;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 10px;
}}

.rn-tagline {{
    font-size: 0.92rem;
    color: #93C5FD;
    margin-top: 4px;
    margin-bottom: 0;
}}

/* Header Badges & Live Status Pills */
.rn-pills-row {{
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 12px;
}}

.rn-badge-sim {{
    background: rgba(245, 158, 11, 0.18);
    color: #FCD34D;
    border: 1px solid #F59E0B;
    border-radius: 9999px;
    padding: 4px 12px;
    font-size: 0.76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}}

.rn-pill-connected {{
    background: rgba(16, 185, 129, 0.2);
    color: #6EE7B7;
    border: 1px solid #10B981;
    border-radius: 9999px;
    padding: 4px 12px;
    font-size: 0.8rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}}

.rn-pill-split {{
    background: rgba(239, 68, 68, 0.2);
    color: #FCA5A5;
    border: 1px solid #EF4444;
    border-radius: 9999px;
    padding: 4px 12px;
    font-size: 0.8rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}}

.rn-pill-converged {{
    background: rgba(16, 185, 129, 0.2);
    color: #6EE7B7;
    border: 1px solid #10B981;
    border-radius: 9999px;
    padding: 4px 12px;
    font-size: 0.8rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}}

.rn-pill-diverged {{
    background: rgba(245, 158, 11, 0.2);
    color: #FCD34D;
    border: 1px solid #F59E0B;
    border-radius: 9999px;
    padding: 4px 12px;
    font-size: 0.8rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}}

/* Main Controls Bar */
.rn-controls-box {{
    background-color: {bg_surface};
    border: 1px solid {border_color};
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 16px;
}}

/* Station Cards */
.station-card {{
    background-color: {bg_surface};
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 16px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    display: flex;
    flex-direction: column;
    gap: 12px;
}}

.station-card-alpha {{
    border: 2px solid #2563EB;
    border-top: 5px solid #2563EB;
}}

.station-card-beta {{
    border: 2px solid #0D9488;
    border-top: 5px solid #0D9488;
}}

.station-card-gamma {{
    border: 2px solid #7C3AED;
    border-top: 5px solid #7C3AED;
}}

.station-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 1px solid {border_subtle};
    padding-bottom: 10px;
    margin-bottom: 4px;
}}

.station-title {{
    font-size: 1.15rem;
    font-weight: 700;
    color: {text_main};
    margin: 0;
}}

.station-role {{
    font-size: 0.82rem;
    color: {text_muted};
    margin: 2px 0 0 0;
}}

/* Sync Status Badges */
.badge-up-to-date {{
    background: rgba(16, 185, 129, 0.16);
    color: #10B981;
    border: 1px solid #10B981;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 0.75rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 5px;
}}

.badge-behind {{
    background: rgba(245, 158, 11, 0.16);
    color: #F59E0B;
    border: 1px solid #F59E0B;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 0.75rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 5px;
}}

/* Version Vector Plain English Display */
.vv-box {{
    background: {bg_surface_alt};
    border: 1px solid {border_subtle};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 0.84rem;
    color: {text_main};
    line-height: 1.35;
}}

.vv-box strong {{
    color: {text_accent};
}}

/* Resource Meters */
.meter-card {{
    background: {bg_surface_alt};
    border: 1px solid {border_subtle};
    border-radius: 8px;
    padding: 10px 12px;
}}

.meter-title {{
    font-size: 0.8rem;
    font-weight: 600;
    color: {text_muted};
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
}}

/* Token Glow Badge */
.token-badge-active {{
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.25) 0%, rgba(217, 119, 6, 0.35) 100%);
    border: 1.5px solid #F59E0B;
    color: #FDE68A;
    padding: 6px 10px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 0.82rem;
    display: flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 0 10px rgba(245, 158, 11, 0.2);
}}

.token-badge-inactive {{
    background: {bg_surface_alt};
    border: 1px dashed {border_color};
    color: {text_muted};
    padding: 6px 10px;
    border-radius: 8px;
    font-size: 0.8rem;
    display: flex;
    align-items: center;
    gap: 6px;
}}

/* Invariants Panel Cards */
.invariant-card {{
    background-color: {bg_surface};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    display: flex;
    align-items: flex-start;
    gap: 12px;
}}

.invariant-card-pass {{
    border-left: 4px solid #10B981;
}}

.invariant-card-warn {{
    border-left: 4px solid #F59E0B;
}}

.invariant-card-fail {{
    border-left: 4px solid #EF4444;
}}

/* Demo Walkthrough Stepper */
.stepper-panel {{
    background: {'#131B2E' if is_dark else '#EFF6FF'};
    border: 1px solid {'#1E3A8A' if is_dark else '#BFDBFE'};
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 16px;
}}

.stepper-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}}

.stepper-script {{
    background: {'#0F172A' if is_dark else '#FFFFFF'};
    border-left: 3px solid #38BDF8;
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 0.88rem;
    margin: 6px 0;
}}

/* Buttons Styling */
button[kind="primary"] {{
    background-color: #2563EB !important;
    border-color: #1D4ED8 !important;
    font-weight: 600 !important;
}}

button[kind="secondary"] {{
    background-color: {bg_surface_alt} !important;
    border-color: {border_color} !important;
    color: {text_main} !important;
}}

/* Monospace code tags */
code {{
    background-color: {bg_surface_alt} !important;
    color: {text_accent} !important;
    border-radius: 4px !important;
    padding: 2px 6px !important;
    font-size: 0.85em !important;
}}
</style>
"""
