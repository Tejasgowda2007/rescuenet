"""
RescueNet Command Center Design System & Custom CSS.
Professional military-grade situational awareness interface:
Dark navy/charcoal background, high-contrast electric cyan and emergency orange accents,
accessible typography, semantic severity badges, and responsive operations cards.
"""

from __future__ import annotations


def get_css(theme: str = "dark") -> str:
    """
    Generate comprehensive CSS design tokens and component styling.
    Strictly adheres to dark-navy/charcoal military command center specifications.
    """
    is_dark = (theme != "light")

    # Color Palette Tokens
    bg_main = "#060A10" if is_dark else "#F4F6F9"
    bg_panel = "#0B121D" if is_dark else "#FFFFFF"
    bg_card = "#101B2B" if is_dark else "#F8FAFC"
    bg_card_elevated = "#16243A" if is_dark else "#EDF2F7"
    border_color = "#1E324D" if is_dark else "#CBD5E1"
    border_subtle = "#142235" if is_dark else "#E2E8F0"
    
    text_primary = "#F0F6FC" if is_dark else "#0F172A"
    text_secondary = "#8B9BB4" if is_dark else "#475569"
    text_muted = "#5C6E87" if is_dark else "#94A3B8"
    
    # Accent Tokens
    cyan_primary = "#00E5FF"
    cyan_glow = "rgba(0, 229, 255, 0.15)"
    orange_emergency = "#FF6B00"
    orange_glow = "rgba(255, 107, 0, 0.15)"
    red_critical = "#EF4444"
    green_online = "#10B981"
    amber_warning = "#F59E0B"

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700;800&display=swap');

/* Global Layout & Background */
html, body, [data-testid="stAppViewContainer"] {{
    background-color: {bg_main} !important;
    color: {text_primary} !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}

[data-testid="stSidebar"] {{
    background-color: {bg_panel} !important;
    border-right: 1px solid {border_color} !important;
}}

/* Top container spacing */
.block-container {{
    padding-top: 1.0rem !important;
    padding-bottom: 2.0rem !important;
    max-width: 1550px !important;
}}

/* Typography */
h1, h2, h3, h4, h5, h6 {{
    color: {text_primary} !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}}

code, pre, .mono {{
    font-family: 'JetBrains Mono', monospace !important;
}}

/* -------------------------------------------------------------------------
   1. COMMAND CENTRE HEADER
   ------------------------------------------------------------------------- */
.rn-header {{
    background: linear-gradient(135deg, #0A1322 0%, #121E33 100%);
    border: 1px solid {cyan_primary}40;
    border-top: 3px solid {cyan_primary};
    border-radius: 8px;
    padding: 16px 22px;
    margin-bottom: 16px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}}

.rn-header-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
}}

.rn-brand {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.rn-logo-badge {{
    background: {cyan_primary}15;
    color: {cyan_primary};
    border: 1.5px solid {cyan_primary};
    border-radius: 6px;
    padding: 6px 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: 0.05em;
}}

.rn-title-group {{
    display: flex;
    flex-direction: column;
}}

.rn-title {{
    font-size: 1.45rem;
    font-weight: 800;
    color: #FFFFFF;
    margin: 0;
    letter-spacing: -0.01em;
    display: flex;
    align-items: center;
    gap: 8px;
}}

.rn-tagline {{
    font-size: 0.85rem;
    color: {cyan_primary};
    font-weight: 500;
    margin-top: 2px;
    letter-spacing: 0.02em;
}}

/* Header Status Pills Row */
.rn-pills-row {{
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid {border_color};
}}

.rn-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.74rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}

.rn-pill-offline {{
    background: rgba(239, 68, 68, 0.15);
    color: #F87171;
    border: 1px solid rgba(239, 68, 68, 0.4);
}}

.rn-pill-mesh-up {{
    background: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.4);
}}

.rn-pill-mesh-split {{
    background: rgba(245, 158, 11, 0.15);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.4);
}}

.rn-pill-cyan {{
    background: rgba(0, 229, 255, 0.12);
    color: {cyan_primary};
    border: 1px solid rgba(0, 229, 255, 0.35);
}}

.rn-pill-crypto {{
    background: rgba(168, 85, 247, 0.15);
    color: #C084FC;
    border: 1px solid rgba(168, 85, 247, 0.4);
}}

/* -------------------------------------------------------------------------
   2. CARDS, PANELS & MATRICES
   ------------------------------------------------------------------------- */
.rn-panel {{
    background: {bg_panel};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
}}

.rn-card {{
    background: {bg_card};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 14px;
    margin-bottom: 12px;
}}

.rn-card-elevated {{
    background: {bg_card_elevated};
    border: 1px solid {cyan_primary}30;
    border-radius: 6px;
    padding: 14px;
    margin-bottom: 12px;
}}

/* -------------------------------------------------------------------------
   3. SEVERITY INDICATORS
   ------------------------------------------------------------------------- */
.badge-critical {{
    background: rgba(239, 68, 68, 0.2);
    color: #FF5A5A;
    border: 1px solid #EF4444;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}}

.badge-high {{
    background: rgba(255, 107, 0, 0.2);
    color: #FFA04D;
    border: 1px solid #FF6B00;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}}

.badge-medium {{
    background: rgba(245, 158, 11, 0.2);
    color: #FCD34D;
    border: 1px solid #F59E0B;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}}

.badge-low {{
    background: rgba(6, 182, 212, 0.18);
    color: #67E8F9;
    border: 1px solid #06B6D4;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}}

/* -------------------------------------------------------------------------
   4. INVARIANT FORMULA BANNER
   ------------------------------------------------------------------------- */
.rn-invariant-banner {{
    background: linear-gradient(90deg, #0A1E2F 0%, #0F2840 100%);
    border: 1px solid {cyan_primary}60;
    border-left: 4px solid {cyan_primary};
    border-radius: 6px;
    padding: 12px 18px;
    margin: 12px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}}

.rn-formula {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.95rem;
    font-weight: 700;
    color: {cyan_primary};
    letter-spacing: 0.04em;
}}

.rn-formula-verified {{
    background: rgba(16, 185, 129, 0.2);
    color: #34D399;
    border: 1px solid #10B981;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 0.75rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
}}

/* -------------------------------------------------------------------------
   5. STEPPER DEMONSTRATION UI
   ------------------------------------------------------------------------- */
.rn-step-card {{
    background: {bg_card};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 14px;
    transition: all 0.2s ease-in-out;
}}

.rn-step-active {{
    background: {bg_card_elevated} !important;
    border: 1.5px solid {cyan_primary} !important;
    box-shadow: 0 0 15px rgba(0, 229, 255, 0.15);
}}

.rn-step-number {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    font-weight: 800;
    color: {cyan_primary};
    margin-bottom: 4px;
}}

.rn-step-title {{
    font-size: 0.95rem;
    font-weight: 700;
    color: #FFFFFF;
}}

.rn-step-desc {{
    font-size: 0.8rem;
    color: {text_secondary};
    margin-top: 4px;
}}

/* -------------------------------------------------------------------------
   6. TABLES & DATA MATRIX
   ------------------------------------------------------------------------- */
.rn-metric-box {{
    background: {bg_card};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 10px 14px;
}}

.rn-metric-label {{
    font-size: 0.72rem;
    color: {text_secondary};
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}

.rn-metric-value {{
    font-size: 1.25rem;
    font-weight: 800;
    color: {text_primary};
    font-family: 'JetBrains Mono', monospace;
    margin-top: 2px;
}}

/* Custom scrollbars */
::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
}}
::-webkit-scrollbar-track {{
    background: {bg_main};
}}
::-webkit-scrollbar-thumb {{
    background: {border_color};
    border-radius: 3px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: {cyan_primary}80;
}}
</style>
"""
