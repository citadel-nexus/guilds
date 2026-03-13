# ZES (Zero-Entry Services) — Complete Implementation Blueprint
## Citadel Nexus Inc. | February 2026

---

# TABLE OF CONTENTS

1. **Brand Identity & Design System**
2. **Supabase Schema — Complete Migration**
3. **Backend — FastAPI Routes & Services (Python)**
4. **Frontend — React Pages & Components**
5. **Metabase — Dashboard Queries & Configuration**
6. **n8n Workflows — Automation Pipelines**
7. **NATS Subjects — Event Architecture**
8. **Stripe — Product & Pricing Configuration**
9. **ElevenLabs — Voice Agent Configuration**
10. **SEO Engine — Per-Tenant Automation**
11. **Deployment — GitLab CI/CD Pipeline**
12. **Go-to-Market — First 10 Customers**

---

# 1. BRAND IDENTITY & DESIGN SYSTEM

## Brand Name
**ZES** — Zero-Entry Services
*Tagline: "The AI employee for your business."*

## Brand Voice
- Speak like a trusted neighbor, not a tech company
- No jargon. Ever. If a barber can't understand it, rewrite it.
- Confident but not arrogant. Helpful but not condescending.
- Active voice: "ZES answers your phone" not "Calls are answered by ZES"

## Color Palette

```css
/* ZES Brand Colors — Add to tailwind.config.js */
:root {
  /* Primary — Trust Blue (professional, reliable) */
  --zes-primary-50: #eff6ff;
  --zes-primary-100: #dbeafe;
  --zes-primary-500: #3b82f6;
  --zes-primary-600: #2563eb;
  --zes-primary-700: #1d4ed8;
  --zes-primary-900: #1e3a5f;

  /* Secondary — Growth Green (money, success, go) */
  --zes-secondary-50: #f0fdf4;
  --zes-secondary-500: #22c55e;
  --zes-secondary-600: #16a34a;

  /* Accent — Warm Amber (friendly, approachable) */
  --zes-accent-50: #fffbeb;
  --zes-accent-500: #f59e0b;
  --zes-accent-600: #d97706;

  /* Neutrals */
  --zes-gray-50: #f9fafb;
  --zes-gray-100: #f3f4f6;
  --zes-gray-500: #6b7280;
  --zes-gray-800: #1f2937;
  --zes-gray-900: #111827;

  /* Tier Colors */
  --zes-scout: #3b82f6;    /* Blue — starter */
  --zes-operator: #8b5cf6; /* Purple — mid */
  --zes-autopilot: #f59e0b; /* Gold — premium */
}
```

## Typography

```css
/* ZES Typography */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Sans:wght@400;500;700&display=swap');

.zes-heading { font-family: 'Inter', sans-serif; font-weight: 800; }
.zes-subheading { font-family: 'Inter', sans-serif; font-weight: 600; }
.zes-body { font-family: 'DM Sans', sans-serif; font-weight: 400; }
.zes-price { font-family: 'Inter', sans-serif; font-weight: 700; }
```

## Tier Badges

| Tier | Name | Icon | Color | Price |
|------|------|------|-------|-------|
| Scout | 🔍 Get Found | Magnifying glass | Blue #3b82f6 | $15/mo |
| Operator | ⚡ Run Smarter | Lightning bolt | Purple #8b5cf6 | $20/mo |
| Autopilot | 🚀 Grow on Autopilot | Rocket | Gold #f59e0b | $30/mo |

---

# 2. SUPABASE SCHEMA — COMPLETE MIGRATION

## File: `supabase/migrations/20260215_zes_complete.sql`

```sql
-- =============================================================
-- ZES (Zero-Entry Services) Complete Schema
-- Migration: 20260215_zes_complete.sql
-- Description: All tables for ZES Scout/Operator/Autopilot tiers
-- SRS: ZES-SCHEMA-001
-- =============================================================

-- =====================
-- 2.1 ZES TENANTS
-- =====================
CREATE TABLE IF NOT EXISTS zes_tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    business_name TEXT NOT NULL,
    industry TEXT NOT NULL CHECK (industry IN (
        'plumbing', 'roofing', 'painting', 'hvac', 'electrical',
        'residential_cleaning', 'commercial_cleaning', 'landscaping',
        'pest_control', 'general_contracting', 'flooring', 'fencing',
        'concrete', 'pool_service', 'tree_service', 'moving',
        'locksmith', 'garage_door', 'pressure_washing', 'handyman',
        'window_cleaning', 'appliance_repair', 'junk_removal',
        'barbershop', 'salon', 'spa', 'restaurant', 'cafe',
        'auto_repair', 'dental', 'veterinary', 'fitness'
    )),
    tier TEXT NOT NULL DEFAULT 'scout' CHECK (tier IN ('scout', 'operator', 'autopilot')),
    business_phone TEXT,
    business_email TEXT,
    business_address JSONB DEFAULT '{}',
    service_area_radius_miles INTEGER DEFAULT 25,
    timezone TEXT DEFAULT 'America/Chicago',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_status TEXT DEFAULT 'trialing' CHECK (subscription_status IN (
        'trialing', 'active', 'past_due', 'canceled', 'paused'
    )),
    trial_ends_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '14 days'),
    website_url TEXT,
    website_status TEXT DEFAULT 'pending' CHECK (website_status IN (
        'pending', 'building', 'live', 'paused', 'error'
    )),
    calcom_event_type_ids JSONB DEFAULT '[]',
    voice_agent_id TEXT,
    voice_agent_enabled BOOLEAN DEFAULT FALSE,
    google_business_profile_id TEXT,
    google_place_id TEXT,
    onboarding_completed_at TIMESTAMPTZ,
    settings JSONB DEFAULT '{
        "review_auto_respond": true,
        "sms_reminders": true,
        "social_posts_per_month": 0,
        "seo_audit_enabled": false,
        "competitor_tracking": false,
        "multi_language": ["en"]
    }',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_tenants_owner ON zes_tenants(owner_id);
CREATE INDEX idx_zes_tenants_industry ON zes_tenants(industry);
CREATE INDEX idx_zes_tenants_tier ON zes_tenants(tier);
CREATE INDEX idx_zes_tenants_status ON zes_tenants(subscription_status);

-- =====================
-- 2.2 ZES LEADS
-- =====================
CREATE TABLE IF NOT EXISTS zes_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN (
        'website_form', 'phone_call', 'voicemail', 'booking',
        'google_review', 'social_media', 'referral', 'walk_in', 'sms'
    )),
    customer_name TEXT,
    customer_phone TEXT,
    customer_email TEXT,
    service_requested TEXT,
    notes TEXT,
    ai_summary TEXT,
    status TEXT DEFAULT 'new' CHECK (status IN (
        'new', 'contacted', 'quoted', 'booked', 'completed',
        'no_show', 'canceled', 'lost'
    )),
    lead_score INTEGER DEFAULT 50 CHECK (lead_score BETWEEN 0 AND 100),
    estimated_value DECIMAL(10,2),
    converted_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_leads_tenant ON zes_leads(tenant_id);
CREATE INDEX idx_zes_leads_status ON zes_leads(status);
CREATE INDEX idx_zes_leads_created ON zes_leads(created_at DESC);

-- =====================
-- 2.3 ZES REVIEWS
-- =====================
CREATE TABLE IF NOT EXISTS zes_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    platform TEXT NOT NULL DEFAULT 'google' CHECK (platform IN (
        'google', 'yelp', 'facebook', 'nextdoor', 'bbb', 'other'
    )),
    reviewer_name TEXT,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    ai_response TEXT,
    ai_response_status TEXT DEFAULT 'pending' CHECK (ai_response_status IN (
        'pending', 'generated', 'approved', 'posted', 'failed'
    )),
    ai_sentiment TEXT CHECK (ai_sentiment IN (
        'very_positive', 'positive', 'neutral', 'negative', 'very_negative'
    )),
    review_url TEXT,
    platform_review_id TEXT,
    responded_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_reviews_tenant ON zes_reviews(tenant_id);
CREATE INDEX idx_zes_reviews_rating ON zes_reviews(rating);
CREATE INDEX idx_zes_reviews_status ON zes_reviews(ai_response_status);

-- =====================
-- 2.4 ZES REVIEW REQUESTS
-- =====================
CREATE TABLE IF NOT EXISTS zes_review_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES zes_leads(id),
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    customer_email TEXT,
    method TEXT DEFAULT 'sms' CHECK (method IN ('sms', 'email', 'both')),
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'sent', 'opened', 'completed', 'expired'
    )),
    review_link TEXT,
    sent_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_review_requests_tenant ON zes_review_requests(tenant_id);

-- =====================
-- 2.5 ZES VOICE CALLS
-- =====================
CREATE TABLE IF NOT EXISTS zes_voice_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    call_sid TEXT UNIQUE,
    direction TEXT CHECK (direction IN ('inbound', 'outbound')),
    caller_number TEXT,
    duration_seconds INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ringing' CHECK (status IN (
        'ringing', 'in_progress', 'completed', 'missed', 'voicemail', 'failed'
    )),
    ai_handled BOOLEAN DEFAULT TRUE,
    ai_transcript TEXT,
    ai_summary TEXT,
    ai_action_taken TEXT,
    booking_created BOOLEAN DEFAULT FALSE,
    lead_id UUID REFERENCES zes_leads(id),
    elevenlabs_conversation_id TEXT,
    recording_url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_voice_calls_tenant ON zes_voice_calls(tenant_id);
CREATE INDEX idx_zes_voice_calls_created ON zes_voice_calls(created_at DESC);

-- =====================
-- 2.6 ZES BOOKINGS
-- =====================
CREATE TABLE IF NOT EXISTS zes_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES zes_leads(id),
    calcom_booking_id TEXT,
    booking_type TEXT CHECK (booking_type IN (
        'free_consultation', 'on_site_estimate', 'service_appointment',
        'follow_up', 'referral_introduction'
    )),
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    customer_email TEXT,
    scheduled_at TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER DEFAULT 30,
    service_description TEXT,
    status TEXT DEFAULT 'confirmed' CHECK (status IN (
        'confirmed', 'rescheduled', 'completed', 'no_show', 'canceled'
    )),
    reminder_sent BOOLEAN DEFAULT FALSE,
    reminder_sent_at TIMESTAMPTZ,
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_bookings_tenant ON zes_bookings(tenant_id);
CREATE INDEX idx_zes_bookings_scheduled ON zes_bookings(scheduled_at);
CREATE INDEX idx_zes_bookings_status ON zes_bookings(status);

-- =====================
-- 2.7 ZES INVOICES
-- =====================
CREATE TABLE IF NOT EXISTS zes_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES zes_leads(id),
    booking_id UUID REFERENCES zes_bookings(id),
    invoice_number TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT,
    customer_phone TEXT,
    line_items JSONB NOT NULL DEFAULT '[]',
    subtotal DECIMAL(10,2) NOT NULL DEFAULT 0,
    tax_rate DECIMAL(5,4) DEFAULT 0,
    tax_amount DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) NOT NULL DEFAULT 0,
    status TEXT DEFAULT 'draft' CHECK (status IN (
        'draft', 'sent', 'viewed', 'paid', 'overdue', 'void'
    )),
    stripe_payment_link TEXT,
    stripe_payment_intent_id TEXT,
    paid_at TIMESTAMPTZ,
    due_date DATE,
    sent_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_invoices_tenant ON zes_invoices(tenant_id);
CREATE INDEX idx_zes_invoices_status ON zes_invoices(status);

-- =====================
-- 2.8 ZES SOCIAL POSTS
-- =====================
CREATE TABLE IF NOT EXISTS zes_social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    platform TEXT CHECK (platform IN ('facebook', 'instagram', 'google_business', 'nextdoor')),
    content TEXT NOT NULL,
    image_url TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN (
        'draft', 'approved', 'scheduled', 'posted', 'failed'
    )),
    scheduled_for TIMESTAMPTZ,
    posted_at TIMESTAMPTZ,
    engagement JSONB DEFAULT '{"likes": 0, "comments": 0, "shares": 0}',
    ai_generated BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_social_posts_tenant ON zes_social_posts(tenant_id);
CREATE INDEX idx_zes_social_posts_status ON zes_social_posts(status);

-- =====================
-- 2.9 ZES SEO AUDITS
-- =====================
CREATE TABLE IF NOT EXISTS zes_seo_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    overall_score INTEGER CHECK (overall_score BETWEEN 0 AND 100),
    title_score INTEGER,
    meta_score INTEGER,
    heading_score INTEGER,
    image_score INTEGER,
    mobile_score INTEGER,
    speed_score INTEGER,
    schema_score INTEGER,
    issues JSONB DEFAULT '[]',
    recommendations JSONB DEFAULT '[]',
    competitor_comparison JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_seo_audits_tenant ON zes_seo_audits(tenant_id);

-- =====================
-- 2.10 ZES COMPETITORS
-- =====================
CREATE TABLE IF NOT EXISTS zes_competitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    competitor_name TEXT NOT NULL,
    competitor_url TEXT,
    google_place_id TEXT,
    average_rating DECIMAL(2,1),
    review_count INTEGER,
    price_data JSONB DEFAULT '{}',
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================
-- 2.11 ZES CUSTOMER MEMORY
-- =====================
CREATE TABLE IF NOT EXISTS zes_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    address JSONB DEFAULT '{}',
    preferences JSONB DEFAULT '{}',
    visit_count INTEGER DEFAULT 0,
    total_spent DECIMAL(10,2) DEFAULT 0,
    last_visit_at TIMESTAMPTZ,
    notes TEXT,
    tags TEXT[] DEFAULT '{}',
    ai_profile_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_customers_tenant ON zes_customers(tenant_id);
CREATE INDEX idx_zes_customers_phone ON zes_customers(phone);

-- =====================
-- 2.12 ZES WEEKLY REPORTS
-- =====================
CREATE TABLE IF NOT EXISTS zes_weekly_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    metrics JSONB NOT NULL DEFAULT '{
        "total_leads": 0,
        "new_bookings": 0,
        "completed_jobs": 0,
        "revenue": 0,
        "reviews_received": 0,
        "average_rating": 0,
        "calls_handled": 0,
        "calls_missed": 0,
        "sms_sent": 0,
        "website_visits": 0
    }',
    ai_insights TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_weekly_reports_tenant ON zes_weekly_reports(tenant_id);

-- =====================
-- 2.13 ZES AUDIT LOG
-- =====================
CREATE TABLE IF NOT EXISTS zes_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES zes_tenants(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    actor TEXT DEFAULT 'system',
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zes_audit_log_tenant ON zes_audit_log(tenant_id);
CREATE INDEX idx_zes_audit_log_created ON zes_audit_log(created_at DESC);

-- =====================
-- RLS POLICIES
-- =====================
ALTER TABLE zes_tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_review_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_voice_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_seo_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_competitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_weekly_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE zes_audit_log ENABLE ROW LEVEL SECURITY;

-- Tenant owner sees only their data
CREATE POLICY zes_tenants_owner ON zes_tenants
    FOR ALL USING (owner_id = auth.uid());

-- All child tables: tenant isolation via tenant_id
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'zes_leads', 'zes_reviews', 'zes_review_requests',
        'zes_voice_calls', 'zes_bookings', 'zes_invoices',
        'zes_social_posts', 'zes_seo_audits', 'zes_competitors',
        'zes_customers', 'zes_weekly_reports', 'zes_audit_log'
    ]) LOOP
        EXECUTE format(
            'CREATE POLICY %I_tenant_isolation ON %I
             FOR ALL USING (
                tenant_id IN (
                    SELECT id FROM zes_tenants WHERE owner_id = auth.uid()
                )
             )',
            t, t
        );
    END LOOP;
END $$;

-- Service role bypass for backend operations
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'zes_tenants', 'zes_leads', 'zes_reviews', 'zes_review_requests',
        'zes_voice_calls', 'zes_bookings', 'zes_invoices',
        'zes_social_posts', 'zes_seo_audits', 'zes_competitors',
        'zes_customers', 'zes_weekly_reports', 'zes_audit_log'
    ]) LOOP
        EXECUTE format(
            'CREATE POLICY %I_service_role ON %I
             FOR ALL USING (
                current_setting($$request.jwt.claims$$, true)::json->>$$role$$ = $$service_role$$
             )',
            t, t
        );
    END LOOP;
END $$;

-- =====================
-- HELPER FUNCTIONS
-- =====================
CREATE OR REPLACE FUNCTION zes_generate_invoice_number(p_tenant_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_count INTEGER;
    v_prefix TEXT;
BEGIN
    SELECT COUNT(*) + 1 INTO v_count
    FROM zes_invoices WHERE tenant_id = p_tenant_id;

    SELECT UPPER(LEFT(REPLACE(business_name, ' ', ''), 3)) INTO v_prefix
    FROM zes_tenants WHERE id = p_tenant_id;

    RETURN v_prefix || '-' || LPAD(v_count::TEXT, 5, '0');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION zes_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER zes_tenants_updated BEFORE UPDATE ON zes_tenants
    FOR EACH ROW EXECUTE FUNCTION zes_update_timestamp();
CREATE TRIGGER zes_leads_updated BEFORE UPDATE ON zes_leads
    FOR EACH ROW EXECUTE FUNCTION zes_update_timestamp();
CREATE TRIGGER zes_bookings_updated BEFORE UPDATE ON zes_bookings
    FOR EACH ROW EXECUTE FUNCTION zes_update_timestamp();
CREATE TRIGGER zes_invoices_updated BEFORE UPDATE ON zes_invoices
    FOR EACH ROW EXECUTE FUNCTION zes_update_timestamp();
CREATE TRIGGER zes_customers_updated BEFORE UPDATE ON zes_customers
    FOR EACH ROW EXECUTE FUNCTION zes_update_timestamp();

-- =====================
-- VIEWS FOR METABASE
-- =====================
CREATE OR REPLACE VIEW v_zes_dashboard_overview AS
SELECT
    t.id AS tenant_id,
    t.business_name,
    t.industry,
    t.tier,
    t.subscription_status,
    (SELECT COUNT(*) FROM zes_leads l WHERE l.tenant_id = t.id AND l.created_at > NOW() - INTERVAL '30 days') AS leads_30d,
    (SELECT COUNT(*) FROM zes_bookings b WHERE b.tenant_id = t.id AND b.status = 'confirmed' AND b.scheduled_at > NOW()) AS upcoming_bookings,
    (SELECT COALESCE(AVG(r.rating), 0) FROM zes_reviews r WHERE r.tenant_id = t.id) AS avg_rating,
    (SELECT COUNT(*) FROM zes_reviews r WHERE r.tenant_id = t.id) AS total_reviews,
    (SELECT COUNT(*) FROM zes_voice_calls vc WHERE vc.tenant_id = t.id AND vc.created_at > NOW() - INTERVAL '30 days') AS calls_30d,
    (SELECT COALESCE(SUM(i.total), 0) FROM zes_invoices i WHERE i.tenant_id = t.id AND i.status = 'paid' AND i.paid_at > NOW() - INTERVAL '30 days') AS revenue_30d
FROM zes_tenants t;

CREATE OR REPLACE VIEW v_zes_lead_funnel AS
SELECT
    tenant_id,
    status,
    COUNT(*) AS count,
    DATE_TRUNC('week', created_at) AS week
FROM zes_leads
GROUP BY tenant_id, status, DATE_TRUNC('week', created_at);

CREATE OR REPLACE VIEW v_zes_review_summary AS
SELECT
    tenant_id,
    platform,
    COUNT(*) AS review_count,
    AVG(rating) AS avg_rating,
    COUNT(*) FILTER (WHERE rating >= 4) AS positive_count,
    COUNT(*) FILTER (WHERE rating <= 2) AS negative_count,
    COUNT(*) FILTER (WHERE ai_response_status = 'posted') AS responded_count
FROM zes_reviews
GROUP BY tenant_id, platform;

CREATE OR REPLACE VIEW v_zes_revenue_trend AS
SELECT
    tenant_id,
    DATE_TRUNC('week', paid_at) AS week,
    COUNT(*) AS invoice_count,
    SUM(total) AS total_revenue,
    AVG(total) AS avg_invoice
FROM zes_invoices
WHERE status = 'paid'
GROUP BY tenant_id, DATE_TRUNC('week', paid_at);

CREATE OR REPLACE VIEW v_zes_voice_analytics AS
SELECT
    tenant_id,
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) AS total_calls,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
    COUNT(*) FILTER (WHERE status = 'missed') AS missed,
    COUNT(*) FILTER (WHERE ai_handled = true) AS ai_handled,
    COUNT(*) FILTER (WHERE booking_created = true) AS bookings_from_calls,
    AVG(duration_seconds) FILTER (WHERE status = 'completed') AS avg_duration
FROM zes_voice_calls
GROUP BY tenant_id, DATE_TRUNC('day', created_at);

-- =====================
-- PLATFORM ADMIN VIEWS
-- =====================
CREATE OR REPLACE VIEW v_zes_platform_mrr AS
SELECT
    tier,
    COUNT(*) AS tenant_count,
    COUNT(*) FILTER (WHERE subscription_status = 'active') AS active,
    COUNT(*) FILTER (WHERE subscription_status = 'trialing') AS trialing,
    COUNT(*) FILTER (WHERE subscription_status = 'canceled') AS churned,
    CASE tier
        WHEN 'scout' THEN COUNT(*) FILTER (WHERE subscription_status = 'active') * 15
        WHEN 'operator' THEN COUNT(*) FILTER (WHERE subscription_status = 'active') * 20
        WHEN 'autopilot' THEN COUNT(*) FILTER (WHERE subscription_status = 'active') * 30
    END AS mrr
FROM zes_tenants
GROUP BY tier;

CREATE OR REPLACE VIEW v_zes_platform_health AS
SELECT
    COUNT(*) AS total_tenants,
    COUNT(*) FILTER (WHERE subscription_status = 'active') AS active_tenants,
    COUNT(*) FILTER (WHERE subscription_status = 'trialing') AS trialing,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') AS new_this_week,
    (SELECT COUNT(*) FROM zes_leads WHERE created_at > NOW() - INTERVAL '24 hours') AS leads_24h,
    (SELECT COUNT(*) FROM zes_voice_calls WHERE created_at > NOW() - INTERVAL '24 hours') AS calls_24h,
    (SELECT COUNT(*) FROM zes_bookings WHERE created_at > NOW() - INTERVAL '24 hours') AS bookings_24h,
    (SELECT COUNT(*) FROM zes_reviews WHERE created_at > NOW() - INTERVAL '7 days') AS reviews_7d
FROM zes_tenants;
```

---

# 3. BACKEND — FASTAPI ROUTES & SERVICES

## File: `src/api/routes/zes_routes.py`

```python
"""
ZES (Zero-Entry Services) API Routes
SRS: ZES-API-001
CGRF: SVC-ZES-001

30 endpoints for Scout/Operator/Autopilot tier features.
Registered in main.py as /api/zes
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date, timedelta
from enum import Enum
import json
import httpx

router = APIRouter(prefix="/api/zes", tags=["ZES"])

# =====================
# MODELS
# =====================

class Industry(str, Enum):
    PLUMBING = "plumbing"
    ROOFING = "roofing"
    PAINTING = "painting"
    HVAC = "hvac"
    ELECTRICAL = "electrical"
    BARBERSHOP = "barbershop"
    SALON = "salon"
    RESTAURANT = "restaurant"
    LANDSCAPING = "landscaping"
    GENERAL_CONTRACTING = "general_contracting"
    # ... all 31 industries

class Tier(str, Enum):
    SCOUT = "scout"
    OPERATOR = "operator"
    AUTOPILOT = "autopilot"

class OnboardRequest(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=200)
    industry: Industry
    tier: Tier = Tier.SCOUT
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    owner_name: str = Field(..., min_length=2)
    service_area_zip: Optional[str] = None

class LeadCreate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    source: str = "website_form"
    service_requested: Optional[str] = None
    notes: Optional[str] = None

class ReviewResponseRequest(BaseModel):
    review_id: str
    tone: str = "professional"  # professional, friendly, apologetic

class InvoiceCreate(BaseModel):
    customer_name: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    line_items: List[dict]  # [{"description": "...", "quantity": 1, "unit_price": 150.00}]
    notes: Optional[str] = None
    due_days: int = 14

class SocialPostRequest(BaseModel):
    topic: Optional[str] = None  # If None, AI picks based on industry + season
    platform: str = "facebook"

class SEOAuditRequest(BaseModel):
    url: Optional[str] = None  # If None, audits tenant's own website

# =====================
# DEPENDENCIES
# =====================

async def get_current_tenant(request: Request):
    """Extract tenant from JWT. Returns tenant record."""
    from src.api.middleware import extract_user_from_jwt
    user = await extract_user_from_jwt(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()
    result = sb.table("zes_tenants").select("*").eq("owner_id", user["id"]).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="No ZES account found. Please onboard first.")
    return result.data

def require_tier(minimum_tier: Tier):
    """Dependency that enforces minimum tier level."""
    tier_levels = {"scout": 1, "operator": 2, "autopilot": 3}
    async def check(tenant=Depends(get_current_tenant)):
        if tier_levels.get(tenant["tier"], 0) < tier_levels[minimum_tier]:
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires {minimum_tier.value} tier or higher. "
                       f"You're on {tenant['tier']}. Upgrade at /pricing"
            )
        return tenant
    return check

# =====================
# 3.1 ONBOARDING
# =====================

@router.post("/onboard")
async def onboard_business(
    data: OnboardRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Create a new ZES tenant. Triggers:
    1. Stripe customer + subscription creation
    2. Website generation via TradeBuilder pipeline
    3. Cal.com event type creation
    4. Voice agent provisioning (Operator+)
    5. Welcome SMS + email
    """
    from src.api.middleware import extract_user_from_jwt
    user = await extract_user_from_jwt(request)
    if not user:
        raise HTTPException(status_code=401)

    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    # Check if already onboarded
    existing = sb.table("zes_tenants").select("id").eq("owner_id", user["id"]).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Already onboarded")

    # Create tenant
    tenant = sb.table("zes_tenants").insert({
        "owner_id": user["id"],
        "business_name": data.business_name,
        "industry": data.industry,
        "tier": data.tier,
        "business_phone": data.business_phone,
        "business_email": data.business_email,
    }).execute()

    tenant_id = tenant.data[0]["id"]

    # Background: provision everything
    background_tasks.add_task(provision_zes_tenant, tenant_id, data)

    return {
        "status": "provisioning",
        "tenant_id": tenant_id,
        "message": f"Setting up {data.business_name}. Your website will be live within 24 hours.",
        "next_steps": [
            "Check your email for login details",
            "Your AI receptionist is being configured" if data.tier != Tier.SCOUT else None,
            "Your website is being built right now"
        ]
    }


async def provision_zes_tenant(tenant_id: str, data: OnboardRequest):
    """Background provisioning pipeline. Maps to existing TradeBuilder infra."""
    import asyncio
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    steps = []

    # Step 1: Create Stripe customer + subscription
    try:
        import stripe
        customer = stripe.Customer.create(
            name=data.owner_name,
            email=data.business_email,
            metadata={"zes_tenant_id": tenant_id, "industry": data.industry}
        )
        price_map = {
            "scout": "price_zes_scout_monthly",      # $15/mo
            "operator": "price_zes_operator_monthly",  # $20/mo
            "autopilot": "price_zes_autopilot_monthly" # $30/mo
        }
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_map[data.tier]}],
            trial_period_days=14,
            metadata={"zes_tenant_id": tenant_id}
        )
        sb.table("zes_tenants").update({
            "stripe_customer_id": customer.id,
            "stripe_subscription_id": subscription.id,
        }).eq("id", tenant_id).execute()
        steps.append("stripe_ok")
    except Exception as e:
        steps.append(f"stripe_error: {e}")

    # Step 2: Trigger website build via TradeBuilder pipeline
    try:
        from src.api.services.tradebuilder_provisioning import provision_site
        await provision_site(
            tenant_id=tenant_id,
            industry=data.industry,
            business_name=data.business_name,
            business_phone=data.business_phone,
        )
        sb.table("zes_tenants").update({
            "website_status": "building"
        }).eq("id", tenant_id).execute()
        steps.append("website_ok")
    except Exception as e:
        steps.append(f"website_error: {e}")

    # Step 3: Create Cal.com booking types based on tier
    try:
        from src.api.services.tradebuilder_integrations.calcom_adapter import create_booking_types
        tier_booking_map = {
            "scout": ["free_consultation"],
            "operator": ["free_consultation", "on_site_estimate", "service_appointment", "follow_up"],
            "autopilot": ["free_consultation", "on_site_estimate", "service_appointment", "follow_up", "referral_introduction"],
        }
        event_type_ids = await create_booking_types(
            tenant_id=tenant_id,
            types=tier_booking_map[data.tier],
            business_name=data.business_name,
        )
        sb.table("zes_tenants").update({
            "calcom_event_type_ids": event_type_ids
        }).eq("id", tenant_id).execute()
        steps.append("calcom_ok")
    except Exception as e:
        steps.append(f"calcom_error: {e}")

    # Step 4: Voice agent (Operator+ only)
    if data.tier in ("operator", "autopilot"):
        try:
            from src.api.services.zes_voice_service import provision_voice_agent
            agent_id = await provision_voice_agent(
                tenant_id=tenant_id,
                business_name=data.business_name,
                industry=data.industry,
                phone=data.business_phone,
            )
            sb.table("zes_tenants").update({
                "voice_agent_id": agent_id,
                "voice_agent_enabled": True,
            }).eq("id", tenant_id).execute()
            steps.append("voice_ok")
        except Exception as e:
            steps.append(f"voice_error: {e}")

    # Step 5: Welcome notification
    try:
        from src.api.services.zes_notification_service import send_welcome
        await send_welcome(
            phone=data.business_phone,
            email=data.business_email,
            business_name=data.business_name,
            tier=data.tier,
        )
        steps.append("welcome_ok")
    except Exception as e:
        steps.append(f"welcome_error: {e}")

    # Mark onboarding complete
    sb.table("zes_tenants").update({
        "onboarding_completed_at": datetime.utcnow().isoformat(),
        "metadata": {"provisioning_steps": steps}
    }).eq("id", tenant_id).execute()

    # Audit log
    sb.table("zes_audit_log").insert({
        "tenant_id": tenant_id,
        "action": "onboarding_complete",
        "entity_type": "tenant",
        "entity_id": tenant_id,
        "details": {"steps": steps, "tier": data.tier}
    }).execute()

    # NATS event
    try:
        from src.lib.nats_service import publish
        await publish("citadel.zes.tenant.provisioned", {
            "tenant_id": tenant_id,
            "tier": data.tier,
            "industry": data.industry,
            "steps": steps,
        })
    except:
        pass


# =====================
# 3.2 DASHBOARD
# =====================

@router.get("/dashboard")
async def get_dashboard(tenant=Depends(get_current_tenant)):
    """Main dashboard — works for all tiers."""
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()
    tid = tenant["id"]

    # Parallel queries
    leads = sb.table("zes_leads").select("*").eq("tenant_id", tid)\
        .gte("created_at", (datetime.utcnow() - timedelta(days=30)).isoformat())\
        .order("created_at", desc=True).limit(20).execute()

    bookings = sb.table("zes_bookings").select("*").eq("tenant_id", tid)\
        .eq("status", "confirmed").gte("scheduled_at", datetime.utcnow().isoformat())\
        .order("scheduled_at").limit(10).execute()

    reviews = sb.table("zes_reviews").select("*").eq("tenant_id", tid)\
        .order("created_at", desc=True).limit(10).execute()

    calls = sb.table("zes_voice_calls").select("*").eq("tenant_id", tid)\
        .gte("created_at", (datetime.utcnow() - timedelta(days=7)).isoformat())\
        .order("created_at", desc=True).limit(20).execute()

    # Metrics
    total_leads = len(leads.data) if leads.data else 0
    avg_rating = 0
    if reviews.data:
        ratings = [r["rating"] for r in reviews.data if r.get("rating")]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0

    return {
        "business": {
            "name": tenant["business_name"],
            "industry": tenant["industry"],
            "tier": tenant["tier"],
            "website_url": tenant.get("website_url"),
            "website_status": tenant.get("website_status"),
        },
        "metrics": {
            "leads_this_month": total_leads,
            "upcoming_bookings": len(bookings.data) if bookings.data else 0,
            "average_rating": avg_rating,
            "total_reviews": len(reviews.data) if reviews.data else 0,
            "calls_this_week": len(calls.data) if calls.data else 0,
        },
        "recent_leads": leads.data[:5] if leads.data else [],
        "upcoming_bookings": bookings.data if bookings.data else [],
        "recent_reviews": reviews.data[:5] if reviews.data else [],
        "recent_calls": calls.data[:5] if calls.data else [] if tenant["tier"] != "scout" else [],
    }


# =====================
# 3.3 LEADS
# =====================

@router.post("/leads")
async def capture_lead(data: LeadCreate, tenant=Depends(get_current_tenant)):
    """Capture a new lead. Can come from website form, phone, or booking."""
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    lead = sb.table("zes_leads").insert({
        "tenant_id": tenant["id"],
        "source": data.source,
        "customer_name": data.customer_name,
        "customer_phone": data.customer_phone,
        "customer_email": data.customer_email,
        "service_requested": data.service_requested,
        "notes": data.notes,
    }).execute()

    # Notify owner via SMS
    if tenant.get("business_phone"):
        from src.api.services.zes_notification_service import send_sms
        await send_sms(
            to=tenant["business_phone"],
            body=f"🔔 New lead! {data.customer_name or 'Someone'} wants {data.service_requested or 'your services'}. "
                 f"Call them: {data.customer_phone or 'no phone'}"
        )

    return {"status": "captured", "lead_id": lead.data[0]["id"]}

@router.get("/leads")
async def list_leads(
    status: Optional[str] = None,
    limit: int = 50,
    tenant=Depends(get_current_tenant)
):
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()
    query = sb.table("zes_leads").select("*").eq("tenant_id", tenant["id"])
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return {"leads": result.data, "count": len(result.data)}


# =====================
# 3.4 REVIEWS — AI RESPONSE
# =====================

@router.post("/reviews/respond")
async def generate_review_response(
    data: ReviewResponseRequest,
    tenant=Depends(get_current_tenant)
):
    """Generate AI response to a Google/Yelp review using Bedrock Haiku."""
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    review = sb.table("zes_reviews").select("*")\
        .eq("id", data.review_id).eq("tenant_id", tenant["id"]).single().execute()
    if not review.data:
        raise HTTPException(status_code=404, detail="Review not found")

    r = review.data

    # Generate response via Bedrock Haiku
    from src.api.services.zes_ai_service import generate_review_response as gen
    response_text = await gen(
        business_name=tenant["business_name"],
        industry=tenant["industry"],
        reviewer_name=r.get("reviewer_name", "Customer"),
        rating=r.get("rating", 5),
        review_text=r.get("review_text", ""),
        tone=data.tone,
    )

    sb.table("zes_reviews").update({
        "ai_response": response_text,
        "ai_response_status": "generated",
    }).eq("id", data.review_id).execute()

    return {
        "review_id": data.review_id,
        "ai_response": response_text,
        "status": "generated",
        "action": "Review and approve, then we'll post it."
    }

@router.post("/reviews/request")
async def send_review_request(
    customer_name: str,
    customer_phone: str,
    tenant=Depends(get_current_tenant)
):
    """Send SMS asking customer to leave a Google review."""
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    review_link = f"https://search.google.com/local/writereview?placeid={tenant.get('google_place_id', '')}"

    from src.api.services.zes_notification_service import send_sms
    await send_sms(
        to=customer_phone,
        body=f"Hi {customer_name}! Thanks for choosing {tenant['business_name']}. "
             f"We'd love a quick Google review — it helps us a lot! {review_link}"
    )

    sb.table("zes_review_requests").insert({
        "tenant_id": tenant["id"],
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "review_link": review_link,
        "status": "sent",
        "sent_at": datetime.utcnow().isoformat(),
    }).execute()

    return {"status": "sent", "message": f"Review request sent to {customer_name}"}


# =====================
# 3.5 VOICE CALLS (Operator+)
# =====================

@router.get("/calls")
async def list_calls(
    limit: int = 50,
    tenant=Depends(require_tier(Tier.OPERATOR))
):
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()
    result = sb.table("zes_voice_calls").select("*")\
        .eq("tenant_id", tenant["id"])\
        .order("created_at", desc=True).limit(limit).execute()
    return {"calls": result.data, "count": len(result.data)}

@router.post("/calls/webhook")
async def voice_call_webhook(request: Request):
    """Webhook from ElevenLabs/Twilio when a call completes."""
    body = await request.json()
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    sb.table("zes_voice_calls").insert({
        "tenant_id": body.get("tenant_id"),
        "call_sid": body.get("call_sid"),
        "direction": body.get("direction", "inbound"),
        "caller_number": body.get("from"),
        "duration_seconds": body.get("duration", 0),
        "status": body.get("status", "completed"),
        "ai_handled": True,
        "ai_transcript": body.get("transcript"),
        "ai_summary": body.get("summary"),
        "ai_action_taken": body.get("action"),
        "booking_created": body.get("booking_created", False),
        "elevenlabs_conversation_id": body.get("conversation_id"),
    }).execute()

    # If booking was created, also create lead
    if body.get("booking_created"):
        sb.table("zes_leads").insert({
            "tenant_id": body["tenant_id"],
            "source": "phone_call",
            "customer_name": body.get("caller_name"),
            "customer_phone": body.get("from"),
            "service_requested": body.get("service_requested"),
            "ai_summary": body.get("summary"),
            "status": "booked",
        }).execute()

    return {"status": "ok"}


# =====================
# 3.6 INVOICING (Operator+)
# =====================

@router.post("/invoices")
async def create_invoice(
    data: InvoiceCreate,
    tenant=Depends(require_tier(Tier.OPERATOR))
):
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    subtotal = sum(item["quantity"] * item["unit_price"] for item in data.line_items)
    tax_rate = 0.0825  # Texas sales tax — make configurable
    tax_amount = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax_amount, 2)
    invoice_number = sb.rpc("zes_generate_invoice_number", {"p_tenant_id": tenant["id"]}).execute().data

    # Create Stripe payment link
    import stripe
    payment_link = stripe.PaymentLink.create(
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Invoice {invoice_number} - {tenant['business_name']}"},
                "unit_amount": int(total * 100),
            },
            "quantity": 1,
        }],
        metadata={"zes_tenant_id": tenant["id"], "invoice_number": invoice_number}
    )

    invoice = sb.table("zes_invoices").insert({
        "tenant_id": tenant["id"],
        "invoice_number": invoice_number,
        "customer_name": data.customer_name,
        "customer_email": data.customer_email,
        "customer_phone": data.customer_phone,
        "line_items": data.line_items,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "stripe_payment_link": payment_link.url,
        "due_date": (date.today() + timedelta(days=data.due_days)).isoformat(),
        "notes": data.notes,
    }).execute()

    # Send invoice via SMS if phone provided
    if data.customer_phone:
        from src.api.services.zes_notification_service import send_sms
        await send_sms(
            to=data.customer_phone,
            body=f"Invoice from {tenant['business_name']}: ${total:.2f}. "
                 f"Pay securely here: {payment_link.url}"
        )

    return {
        "invoice_id": invoice.data[0]["id"],
        "invoice_number": invoice_number,
        "total": total,
        "payment_link": payment_link.url,
        "status": "sent" if data.customer_phone else "draft"
    }


# =====================
# 3.7 SOCIAL POSTS (Operator+)
# =====================

@router.post("/social/generate")
async def generate_social_post(
    data: SocialPostRequest,
    tenant=Depends(require_tier(Tier.OPERATOR))
):
    """AI generates a social media post for the business."""
    from src.api.services.zes_ai_service import generate_social_post as gen
    post_content = await gen(
        business_name=tenant["business_name"],
        industry=tenant["industry"],
        topic=data.topic,
        platform=data.platform,
    )

    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()
    post = sb.table("zes_social_posts").insert({
        "tenant_id": tenant["id"],
        "platform": data.platform,
        "content": post_content,
        "status": "draft",
    }).execute()

    return {
        "post_id": post.data[0]["id"],
        "content": post_content,
        "platform": data.platform,
        "status": "draft",
        "action": "Approve this post and we'll schedule it."
    }


# =====================
# 3.8 SEO AUDIT (Autopilot)
# =====================

@router.post("/seo/audit")
async def run_seo_audit(
    data: SEOAuditRequest,
    tenant=Depends(require_tier(Tier.AUTOPILOT))
):
    """Run SEO audit on tenant's website. Reuses LIGHTHOUSE engine."""
    url = data.url or tenant.get("website_url")
    if not url:
        raise HTTPException(status_code=400, detail="No URL to audit")

    # Call existing SEO engine
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/seo/audit",
            json={"url": url},
            timeout=30,
        )
    audit_result = resp.json()

    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()
    sb.table("zes_seo_audits").insert({
        "tenant_id": tenant["id"],
        "url": url,
        "overall_score": audit_result.get("overall_score"),
        "title_score": audit_result.get("title_score"),
        "meta_score": audit_result.get("meta_score"),
        "issues": audit_result.get("issues", []),
        "recommendations": audit_result.get("recommendations", []),
    }).execute()

    return audit_result


# =====================
# 3.9 COMPETITOR MONITORING (Autopilot)
# =====================

@router.post("/competitors/add")
async def add_competitor(
    name: str,
    url: Optional[str] = None,
    tenant=Depends(require_tier(Tier.AUTOPILOT))
):
    from src.api.services.supabase_client import get_supabase
    sb = get_supabase()

    # Check limit (1 competitor for Autopilot)
    existing = sb.table("zes_competitors").select("id").eq("tenant_id", tenant["id"]).execute()
    if len(existing.data) >= 1:
        raise HTTPException(status_code=400, detail="Autopilot includes 1 competitor. Upgrade for more.")

    competitor = sb.table("zes_competitors").insert({
        "tenant_id": tenant["id"],
        "competitor_name": name,
        "competitor_url": url,
    }).execute()

    return {"competitor_id": competitor.data[0]["id"], "status": "added"}


# =====================
# 3.10 HEALTH & PLATFORM
# =====================

@router.get("/health")
async def health():
    return {"status": "ok", "service": "zes", "version": "1.0.0"}

@router.get("/tiers")
async def get_tiers():
    """Public endpoint — returns ZES tier information."""
    return {
        "tiers": [
            {
                "id": "scout",
                "name": "ZES Scout",
                "tagline": "Get Found",
                "price": 15,
                "features": [
                    "Professional trade website (live in 24 hours)",
                    "Online booking page",
                    "Automated Google review requests",
                    "AI-powered review responses",
                    "Lead capture + SMS notifications",
                    "Weekly AI business email",
                    "Basic dashboard",
                ],
            },
            {
                "id": "operator",
                "name": "ZES Operator",
                "tagline": "Run Smarter",
                "price": 20,
                "popular": True,
                "features": [
                    "Everything in Scout, plus:",
                    "AI voice receptionist (24/7 phone answering)",
                    "4 booking types (estimates, service, follow-up)",
                    "AI-generated invoices + payment links",
                    "Customer memory (preferences, history)",
                    "4 social media posts/month",
                    "SMS appointment reminders",
                ],
            },
            {
                "id": "autopilot",
                "name": "ZES Autopilot",
                "tagline": "Grow on Autopilot",
                "price": 30,
                "features": [
                    "Everything in Operator, plus:",
                    "Monthly automated SEO audit",
                    "Edit your website anytime",
                    "Business intelligence dashboard",
                    "Autonomous rescheduling + waitlist",
                    "Competitor price monitoring",
                    '"AI-Governed by Citadel" trust badge',
                    "Monthly group strategy call",
                ],
            },
        ]
    }
```

## File: `src/api/services/zes_ai_service.py`

```python
"""
ZES AI Service — All LLM calls via AWS Bedrock Haiku
SRS: ZES-AI-001
Cost: ~$0.25 per 1M input tokens (Haiku) = sub-cent per operation
"""

import json
import boto3
from datetime import datetime

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"


async def _call_haiku(system: str, user: str, max_tokens: int = 500) -> str:
    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }),
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


async def generate_review_response(
    business_name: str,
    industry: str,
    reviewer_name: str,
    rating: int,
    review_text: str,
    tone: str = "professional",
) -> str:
    system = f"""You write review responses for {business_name}, a {industry} business.
Rules:
- Be {tone}, warm, and genuine
- Thank them by first name
- If positive (4-5 stars): express gratitude, mention specific praise they gave
- If negative (1-2 stars): apologize sincerely, offer to make it right, provide contact info
- If neutral (3 stars): thank them, ask how you can improve
- Keep it under 100 words
- Never be defensive or argue
- Sign off with the business name"""

    user = f"Review from {reviewer_name} ({rating}/5 stars):\n{review_text}"
    return await _call_haiku(system, user, max_tokens=200)


async def generate_social_post(
    business_name: str,
    industry: str,
    topic: str = None,
    platform: str = "facebook",
) -> str:
    month = datetime.now().strftime("%B")
    system = f"""You write social media posts for {business_name}, a {industry} business.
Rules:
- Write for {platform}
- Be conversational and relatable, not corporate
- Include 1-2 relevant emojis
- Include a call-to-action (book now, call us, etc.)
- Keep it under 150 words
- It's {month} — reference seasonal topics if relevant
- No hashtag spam (max 3 hashtags)"""

    user = topic or f"Write a post showcasing our {industry} services this {month}"
    return await _call_haiku(system, user, max_tokens=250)


async def generate_weekly_insights(
    business_name: str,
    metrics: dict,
) -> str:
    system = f"""You write weekly business insight emails for {business_name}.
Rules:
- Be encouraging and actionable
- Reference specific numbers from the metrics
- Give 1-2 concrete tips to improve
- Keep it under 200 words
- Write like a friendly business advisor, not a robot"""

    user = f"Weekly metrics: {json.dumps(metrics)}"
    return await _call_haiku(system, user, max_tokens=400)


async def generate_lead_summary(
    business_name: str,
    call_transcript: str,
) -> str:
    system = f"""Summarize this phone call for {business_name} in 2-3 sentences.
Include: what they need, when they need it, and any urgency."""
    return await _call_haiku(system, call_transcript, max_tokens=100)
```

## File: `src/api/services/zes_notification_service.py`

```python
"""
ZES Notification Service — SMS via Twilio, Email via Resend/SES
SRS: ZES-NOTIFY-001
"""

import os
from twilio.rest import Client as TwilioClient

twilio = TwilioClient(
    os.environ.get("TWILIO_ACCOUNT_SID"),
    os.environ.get("TWILIO_AUTH_TOKEN"),
)
TWILIO_FROM = os.environ.get("TWILIO_FROM_NUMBER", "+18325551234")


async def send_sms(to: str, body: str):
    """Send SMS via Twilio. Cost: ~$0.0079 per message."""
    try:
        twilio.messages.create(
            to=to,
            from_=TWILIO_FROM,
            body=body,
        )
    except Exception as e:
        print(f"SMS failed to {to}: {e}")


async def send_welcome(phone: str, email: str, business_name: str, tier: str):
    """Send welcome SMS + email after onboarding."""
    tier_names = {"scout": "Scout", "operator": "Operator", "autopilot": "Autopilot"}

    if phone:
        await send_sms(
            to=phone,
            body=f"🎉 Welcome to ZES {tier_names[tier]}! "
                 f"{business_name} is being set up right now. "
                 f"Your website will be live within 24 hours. "
                 f"We'll text you when everything's ready!"
        )

    # Email via existing infrastructure or Resend
    # TODO: Wire to Intercom or Resend for HTML emails


async def send_booking_reminder(phone: str, business_name: str, customer_name: str, time: str):
    """Send appointment reminder SMS 24h before."""
    await send_sms(
        to=phone,
        body=f"Reminder: You have an appointment with {business_name} tomorrow at {time}. "
             f"Reply RESCHEDULE to change or CANCEL to cancel."
    )


async def send_review_request_sms(phone: str, business_name: str, customer_name: str, review_link: str):
    await send_sms(
        to=phone,
        body=f"Hi {customer_name}! Thanks for choosing {business_name}. "
             f"We'd love a quick Google review — it helps us a lot! {review_link}"
    )
```

---

# 4. FRONTEND — REACT PAGES & COMPONENTS

## File: `src/pages/ZES.jsx` — Landing Page

```jsx
import React from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ZESPricingTable from '../components/ZESPricingTable';

const ZES_INDUSTRIES = [
  { name: 'Barbershops', icon: '💈', color: 'blue' },
  { name: 'Plumbers', icon: '🔧', color: 'blue' },
  { name: 'HVAC', icon: '❄️', color: 'cyan' },
  { name: 'Electricians', icon: '⚡', color: 'yellow' },
  { name: 'Roofers', icon: '🏠', color: 'orange' },
  { name: 'Salons', icon: '✂️', color: 'pink' },
  { name: 'Restaurants', icon: '🍕', color: 'red' },
  { name: 'Landscapers', icon: '🌿', color: 'green' },
  { name: 'Auto Repair', icon: '🚗', color: 'gray' },
  { name: 'Cleaners', icon: '🧹', color: 'purple' },
  { name: 'Painters', icon: '🎨', color: 'indigo' },
  { name: 'Movers', icon: '📦', color: 'amber' },
];

const COMPETITOR_PRICES = [
  { name: 'Podium', price: '$399/mo', feature: 'Reviews + messaging' },
  { name: 'Broadly', price: '$299/mo', feature: 'Reputation + SEO' },
  { name: 'GoHighLevel', price: '$97/mo', feature: 'CRM + funnels' },
  { name: 'AI Receptionist', price: '$199/mo', feature: 'Phone answering' },
  { name: 'Jobber', price: '$59/mo', feature: 'Scheduling' },
];

export default function ZESLanding() {
  return (
    <div className="min-h-screen bg-white">
      {/* HERO */}
      <section className="relative overflow-hidden bg-gradient-to-br from-zes-primary-900 to-zes-primary-700 text-white">
        <div className="max-w-6xl mx-auto px-4 py-20 sm:py-28 text-center">
          <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur rounded-full px-4 py-1.5 mb-6">
            <span className="text-zes-accent-500 font-semibold">NEW</span>
            <span className="text-sm">14-day free trial. No credit card.</span>
          </div>

          <h1 className="text-4xl sm:text-6xl font-extrabold leading-tight mb-6">
            The AI Employee<br/>
            <span className="text-zes-accent-500">for Your Business</span>
          </h1>

          <p className="text-xl sm:text-2xl text-blue-100 max-w-3xl mx-auto mb-8">
            ZES answers your phone 24/7, books appointments, sends invoices,
            gets you Google reviews, and shows you how your business is doing —
            <strong className="text-white"> all for $15–$30/month.</strong>
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-12">
            <Link
              to="/zes/onboard"
              className="bg-zes-accent-500 hover:bg-zes-accent-600 text-black font-bold px-8 py-4 rounded-xl text-lg transition-all shadow-lg hover:shadow-xl"
            >
              Start Free Trial →
            </Link>
            <a
              href="#pricing"
              className="border-2 border-white/30 hover:border-white text-white font-semibold px-8 py-4 rounded-xl text-lg transition-all"
            >
              See Pricing
            </a>
          </div>

          {/* Competitor price comparison */}
          <div className="bg-white/5 backdrop-blur rounded-2xl p-6 max-w-2xl mx-auto">
            <p className="text-sm text-blue-200 mb-3">What others charge for LESS:</p>
            <div className="flex flex-wrap justify-center gap-3">
              {COMPETITOR_PRICES.map(c => (
                <div key={c.name} className="bg-white/10 rounded-lg px-3 py-2 text-sm">
                  <span className="line-through text-red-300">{c.price}</span>
                  <span className="text-blue-200 ml-1">{c.name}</span>
                </div>
              ))}
            </div>
            <p className="text-zes-accent-500 font-bold mt-3 text-lg">
              ZES does ALL of this for $30/month.
            </p>
          </div>
        </div>
      </section>

      {/* WHAT YOU GET */}
      <section className="max-w-6xl mx-auto px-4 py-20">
        <h2 className="text-3xl sm:text-4xl font-extrabold text-center mb-4">
          Everything Your Business Needs. One Price.
        </h2>
        <p className="text-gray-500 text-center text-lg mb-12 max-w-2xl mx-auto">
          No tech skills required. Tell us your trade — we handle the rest.
        </p>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[
            {
              icon: '🌐', title: 'Professional Website',
              desc: 'Built for your trade, live in 24 hours. Mobile-optimized with booking built in.',
              tier: 'Scout'
            },
            {
              icon: '📞', title: 'AI Phone Receptionist',
              desc: 'Never miss a call. AI answers, books appointments, and texts you the summary.',
              tier: 'Operator'
            },
            {
              icon: '⭐', title: 'Google Review Autopilot',
              desc: 'Automatically asks happy customers for reviews. AI writes your responses.',
              tier: 'Scout'
            },
            {
              icon: '📅', title: 'Online Booking',
              desc: 'Customers book online. You get a text. No more phone tag.',
              tier: 'Scout'
            },
            {
              icon: '💰', title: 'Instant Invoicing',
              desc: 'Tap a button after a job. Customer gets a payment link. Money in your account.',
              tier: 'Operator'
            },
            {
              icon: '📊', title: 'Business Dashboard',
              desc: 'See leads, bookings, revenue, and reviews — all in one place.',
              tier: 'Autopilot'
            },
            {
              icon: '📱', title: 'Social Media Posts',
              desc: '4 ready-to-post updates every month. AI writes them for your trade.',
              tier: 'Operator'
            },
            {
              icon: '🔍', title: 'SEO Monitoring',
              desc: 'Monthly audit of your website. See how you rank for "plumber near me."',
              tier: 'Autopilot'
            },
            {
              icon: '🛡️', title: 'Job Documentation',
              desc: 'Every job, invoice, and communication — timestamped and stored.',
              tier: 'Scout'
            },
          ].map(f => (
            <div key={f.title} className="bg-gray-50 rounded-2xl p-6 hover:shadow-md transition-all border border-gray-100">
              <div className="text-3xl mb-3">{f.icon}</div>
              <h3 className="font-bold text-lg mb-2">{f.title}</h3>
              <p className="text-gray-600 text-sm mb-3">{f.desc}</p>
              <span className={`inline-block text-xs font-semibold px-2 py-1 rounded-full ${
                f.tier === 'Scout' ? 'bg-blue-100 text-blue-700' :
                f.tier === 'Operator' ? 'bg-purple-100 text-purple-700' :
                'bg-amber-100 text-amber-700'
              }`}>
                {f.tier} — ${f.tier === 'Scout' ? '15' : f.tier === 'Operator' ? '20' : '30'}/mo
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* INDUSTRIES */}
      <section className="bg-gray-50 py-20">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-extrabold mb-4">
            Built for Your Trade
          </h2>
          <p className="text-gray-500 mb-8">
            Custom AI trained for 30+ industries. Your website, voice agent, and content
            are tailored to exactly what you do.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            {ZES_INDUSTRIES.map(ind => (
              <div key={ind.name} className="bg-white rounded-xl px-4 py-3 shadow-sm border border-gray-100 flex items-center gap-2">
                <span className="text-xl">{ind.icon}</span>
                <span className="font-medium text-gray-700">{ind.name}</span>
              </div>
            ))}
            <div className="bg-white rounded-xl px-4 py-3 shadow-sm border border-gray-100 flex items-center gap-2">
              <span className="text-xl">➕</span>
              <span className="font-medium text-gray-500">20+ more</span>
            </div>
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="max-w-6xl mx-auto px-4 py-20">
        <ZESPricingTable />
      </section>

      {/* CTA */}
      <section className="bg-zes-primary-900 text-white py-16">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-extrabold mb-4">
            Your Business, Upgraded in 24 Hours
          </h2>
          <p className="text-blue-200 text-lg mb-8">
            14-day free trial. No credit card required. Cancel anytime.
          </p>
          <Link
            to="/zes/onboard"
            className="inline-block bg-zes-accent-500 hover:bg-zes-accent-600 text-black font-bold px-10 py-4 rounded-xl text-xl transition-all shadow-lg"
          >
            Start Free Trial →
          </Link>
        </div>
      </section>
    </div>
  );
}
```

## File: `src/components/ZESPricingTable.jsx`

```jsx
import React, { useState } from 'react';
import { Link } from 'react-router-dom';

const TIERS = [
  {
    id: 'scout',
    name: 'Scout',
    tagline: 'Get Found',
    price: 15,
    icon: '🔍',
    color: 'blue',
    popular: false,
    features: [
      { text: 'Professional trade website', included: true },
      { text: 'Online booking (free consultations)', included: true },
      { text: 'Google review request automation', included: true },
      { text: 'AI review response generator', included: true },
      { text: 'Lead capture + SMS alerts', included: true },
      { text: 'Weekly AI business email', included: true },
      { text: 'Basic dashboard', included: true },
      { text: 'AI phone receptionist', included: false },
      { text: 'Invoicing + payments', included: false },
      { text: 'Social media posts', included: false },
      { text: 'SEO audit', included: false },
    ],
  },
  {
    id: 'operator',
    name: 'Operator',
    tagline: 'Run Smarter',
    price: 20,
    icon: '⚡',
    color: 'purple',
    popular: true,
    features: [
      { text: 'Everything in Scout', included: true, bold: true },
      { text: 'AI phone receptionist (24/7)', included: true, highlight: true },
      { text: '4 booking types', included: true },
      { text: 'AI invoicing + Stripe payments', included: true },
      { text: 'Customer memory + preferences', included: true },
      { text: '4 social media posts/month', included: true },
      { text: 'SMS appointment reminders', included: true },
      { text: 'Bilingual support (EN/ES)', included: true },
      { text: 'SEO audit', included: false },
      { text: 'Competitor monitoring', included: false },
    ],
  },
  {
    id: 'autopilot',
    name: 'Autopilot',
    tagline: 'Grow on Autopilot',
    price: 30,
    icon: '🚀',
    color: 'amber',
    popular: false,
    features: [
      { text: 'Everything in Operator', included: true, bold: true },
      { text: 'Monthly SEO audit + recommendations', included: true, highlight: true },
      { text: 'Edit your website anytime', included: true },
      { text: 'Business intelligence dashboard', included: true },
      { text: 'Autonomous rescheduling + waitlist', included: true },
      { text: 'Competitor price monitoring', included: true },
      { text: '"AI-Governed" trust badge', included: true },
      { text: 'Monthly group strategy call', included: true },
      { text: '5 booking types + referrals', included: true },
      { text: 'All 5 languages', included: true },
    ],
  },
];

export default function ZESPricingTable() {
  return (
    <div>
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-extrabold mb-4">
          Simple Pricing. No Surprises.
        </h2>
        <p className="text-gray-500 text-lg">
          14-day free trial on every plan. No credit card required. Cancel anytime.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
        {TIERS.map(tier => (
          <div
            key={tier.id}
            className={`relative rounded-2xl border-2 p-6 transition-all hover:shadow-lg ${
              tier.popular
                ? 'border-purple-500 shadow-md scale-[1.02]'
                : 'border-gray-200'
            }`}
          >
            {tier.popular && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-purple-500 text-white text-xs font-bold px-4 py-1 rounded-full">
                MOST POPULAR
              </div>
            )}

            <div className="text-center mb-6">
              <span className="text-3xl">{tier.icon}</span>
              <h3 className="text-xl font-bold mt-2">{tier.name}</h3>
              <p className="text-gray-500 text-sm">{tier.tagline}</p>
              <div className="mt-4">
                <span className="text-4xl font-extrabold">${tier.price}</span>
                <span className="text-gray-400">/mo</span>
              </div>
            </div>

            <ul className="space-y-3 mb-8">
              {tier.features.map((f, i) => (
                <li key={i} className={`flex items-start gap-2 text-sm ${
                  !f.included ? 'text-gray-300' : f.highlight ? 'text-purple-700 font-semibold' : 'text-gray-700'
                }`}>
                  <span className={`mt-0.5 ${f.included ? 'text-green-500' : 'text-gray-300'}`}>
                    {f.included ? '✓' : '—'}
                  </span>
                  <span className={f.bold ? 'font-semibold' : ''}>{f.text}</span>
                </li>
              ))}
            </ul>

            <Link
              to={`/zes/onboard?tier=${tier.id}`}
              className={`block text-center py-3 rounded-xl font-semibold transition-all ${
                tier.popular
                  ? 'bg-purple-600 text-white hover:bg-purple-700'
                  : 'bg-gray-100 text-gray-800 hover:bg-gray-200'
              }`}
            >
              Start Free Trial
            </Link>
          </div>
        ))}
      </div>

      <p className="text-center text-gray-400 text-sm mt-8">
        All plans include 14-day free trial. No contracts. No setup fees.
        Prices in USD. Cancel anytime from your dashboard.
      </p>
    </div>
  );
}
```

---

# 5. METABASE — DASHBOARD QUERIES

## Dashboard: "ZES Platform Overview" (Admin)

### Query 1: MRR by Tier
```sql
SELECT
  tier,
  COUNT(*) FILTER (WHERE subscription_status = 'active') AS active,
  COUNT(*) FILTER (WHERE subscription_status = 'trialing') AS trialing,
  CASE tier
    WHEN 'scout' THEN COUNT(*) FILTER (WHERE subscription_status = 'active') * 15
    WHEN 'operator' THEN COUNT(*) FILTER (WHERE subscription_status = 'active') * 20
    WHEN 'autopilot' THEN COUNT(*) FILTER (WHERE subscription_status = 'active') * 30
  END AS mrr
FROM zes_tenants
GROUP BY tier
ORDER BY mrr DESC;
```

### Query 2: Daily Lead Volume
```sql
SELECT
  DATE(created_at) AS day,
  COUNT(*) AS total_leads,
  COUNT(*) FILTER (WHERE source = 'phone_call') AS from_calls,
  COUNT(*) FILTER (WHERE source = 'booking') AS from_bookings,
  COUNT(*) FILTER (WHERE source = 'website_form') AS from_website
FROM zes_leads
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY day;
```

### Query 3: Review Performance
```sql
SELECT
  t.business_name,
  t.industry,
  COUNT(r.id) AS total_reviews,
  ROUND(AVG(r.rating), 1) AS avg_rating,
  COUNT(*) FILTER (WHERE r.rating >= 4) AS positive,
  COUNT(*) FILTER (WHERE r.rating <= 2) AS negative,
  COUNT(*) FILTER (WHERE r.ai_response_status = 'posted') AS ai_responded
FROM zes_tenants t
LEFT JOIN zes_reviews r ON r.tenant_id = t.id
GROUP BY t.id, t.business_name, t.industry
ORDER BY total_reviews DESC;
```

### Query 4: Voice Call Analytics (Operator+ Tenants)
```sql
SELECT
  DATE(vc.created_at) AS day,
  COUNT(*) AS total_calls,
  COUNT(*) FILTER (WHERE vc.status = 'completed') AS completed,
  COUNT(*) FILTER (WHERE vc.status = 'missed') AS missed,
  ROUND(AVG(vc.duration_seconds) FILTER (WHERE vc.status = 'completed')) AS avg_duration,
  COUNT(*) FILTER (WHERE vc.booking_created = true) AS converted_to_booking,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE vc.booking_created = true) /
    NULLIF(COUNT(*), 0), 1
  ) AS conversion_rate
FROM zes_voice_calls vc
WHERE vc.created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(vc.created_at)
ORDER BY day;
```

### Query 5: Revenue by Tenant
```sql
SELECT
  t.business_name,
  t.industry,
  t.tier,
  COUNT(i.id) AS invoices,
  COALESCE(SUM(i.total) FILTER (WHERE i.status = 'paid'), 0) AS collected,
  COALESCE(SUM(i.total) FILTER (WHERE i.status = 'sent'), 0) AS outstanding
FROM zes_tenants t
LEFT JOIN zes_invoices i ON i.tenant_id = t.id
GROUP BY t.id, t.business_name, t.industry, t.tier
ORDER BY collected DESC;
```

### Query 6: Churn Risk
```sql
SELECT
  t.business_name,
  t.tier,
  t.subscription_status,
  t.created_at AS joined,
  (SELECT MAX(created_at) FROM zes_leads l WHERE l.tenant_id = t.id) AS last_lead,
  (SELECT COUNT(*) FROM zes_leads l WHERE l.tenant_id = t.id AND l.created_at > NOW() - INTERVAL '7 days') AS leads_7d,
  (SELECT COUNT(*) FROM zes_voice_calls vc WHERE vc.tenant_id = t.id AND vc.created_at > NOW() - INTERVAL '7 days') AS calls_7d,
  CASE
    WHEN (SELECT COUNT(*) FROM zes_leads l WHERE l.tenant_id = t.id AND l.created_at > NOW() - INTERVAL '14 days') = 0
    THEN 'HIGH RISK'
    WHEN (SELECT COUNT(*) FROM zes_leads l WHERE l.tenant_id = t.id AND l.created_at > NOW() - INTERVAL '7 days') = 0
    THEN 'MEDIUM RISK'
    ELSE 'HEALTHY'
  END AS churn_risk
FROM zes_tenants t
WHERE t.subscription_status = 'active'
ORDER BY churn_risk DESC;
```

## Dashboard: "My Business" (Per-Tenant Embed via JWT)

### Metabase JWT Embed Config
```python
# src/api/services/zes_metabase_embed.py

import jwt
import time
import os

METABASE_SITE_URL = "https://metabase.citadel-nexus.com"
METABASE_SECRET_KEY = os.environ["METABASE_EMBEDDING_SECRET_KEY"]

def get_tenant_dashboard_url(tenant_id: str, dashboard_id: int = 10) -> str:
    payload = {
        "resource": {"dashboard": dashboard_id},
        "params": {"tenant_id": tenant_id},
        "exp": round(time.time()) + (60 * 10),  # 10 min
    }
    token = jwt.encode(payload, METABASE_SECRET_KEY, algorithm="HS256")
    return f"{METABASE_SITE_URL}/embed/dashboard/{token}#bordered=false&titled=false"
```

---

# 6. N8N WORKFLOWS

## Workflow: ZES Weekly Report Generator
```json
{
  "name": "ZES Weekly Report",
  "trigger": "cron",
  "schedule": "0 9 * * 1",
  "nodes": [
    {
      "name": "Fetch Active Tenants",
      "type": "Supabase",
      "action": "SELECT * FROM zes_tenants WHERE subscription_status = 'active'"
    },
    {
      "name": "For Each Tenant",
      "type": "SplitInBatches",
      "batchSize": 1
    },
    {
      "name": "Gather Metrics",
      "type": "Supabase",
      "action": "SELECT * FROM v_zes_dashboard_overview WHERE tenant_id = {{$json.id}}"
    },
    {
      "name": "Generate AI Insights",
      "type": "HTTP Request",
      "url": "http://localhost:8000/api/zes/internal/weekly-insights",
      "method": "POST",
      "body": {
        "tenant_id": "{{$json.tenant_id}}",
        "metrics": "{{$json.metrics}}"
      }
    },
    {
      "name": "Store Report",
      "type": "Supabase",
      "action": "INSERT INTO zes_weekly_reports"
    },
    {
      "name": "Send Email",
      "type": "SendEmail",
      "to": "{{$json.business_email}}",
      "subject": "📊 Your Weekly Business Report — {{$json.business_name}}"
    }
  ]
}
```

## Workflow: ZES Review Request After Booking Complete
```json
{
  "name": "ZES Review Request on Job Complete",
  "trigger": "NATS",
  "subject": "citadel.zes.booking.completed",
  "nodes": [
    {
      "name": "Wait 2 Hours",
      "type": "Wait",
      "duration": "2h"
    },
    {
      "name": "Fetch Tenant",
      "type": "Supabase",
      "action": "SELECT * FROM zes_tenants WHERE id = {{$json.tenant_id}}"
    },
    {
      "name": "Send Review SMS",
      "type": "HTTP Request",
      "url": "http://localhost:8000/api/zes/reviews/request",
      "method": "POST"
    },
    {
      "name": "Log to Audit",
      "type": "Supabase",
      "action": "INSERT INTO zes_audit_log"
    }
  ]
}
```

---

# 7. NATS SUBJECTS

| Subject | Producer | Consumer | Description |
|---------|----------|----------|-------------|
| `citadel.zes.tenant.provisioned` | ZES API | n8n, Slack | New tenant onboarded |
| `citadel.zes.tenant.upgraded` | Stripe webhook | n8n | Tier upgrade |
| `citadel.zes.tenant.churned` | Stripe webhook | n8n, Slack | Subscription canceled |
| `citadel.zes.lead.captured` | ZES API, Voice | n8n, Lead Hunter | New lead created |
| `citadel.zes.booking.created` | Cal.com bridge | n8n | New booking |
| `citadel.zes.booking.completed` | ZES API | n8n (review request) | Job marked done |
| `citadel.zes.booking.canceled` | Cal.com bridge | n8n | Booking canceled |
| `citadel.zes.call.completed` | ElevenLabs webhook | n8n | Voice call ended |
| `citadel.zes.call.missed` | Twilio webhook | n8n (text-back) | Missed call |
| `citadel.zes.review.received` | Google webhook | n8n (AI response) | New review |
| `citadel.zes.invoice.paid` | Stripe webhook | n8n, Xero | Invoice paid |
| `citadel.zes.seo.audit.complete` | SEO cron | n8n (email) | Monthly audit done |
| `citadel.zes.social.approved` | ZES API | n8n (auto-post) | Social post approved |
| `citadel.zes.weekly.report` | n8n cron | email service | Weekly report ready |

---

# 8. STRIPE PRODUCTS

```python
# tools/zes_stripe_setup.py
# Run once: python tools/zes_stripe_setup.py

import stripe
import os

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

products = [
    {
        "name": "ZES Scout",
        "description": "Professional website, booking, reviews, lead capture — $15/mo",
        "price": 1500,
        "metadata": {"zes_tier": "scout"},
        "features": [
            "Professional trade website",
            "Online booking page",
            "Google review automation",
            "AI review responses",
            "Lead capture + SMS alerts",
            "Weekly AI business email",
            "Basic dashboard",
        ],
    },
    {
        "name": "ZES Operator",
        "description": "AI receptionist, invoicing, social posts — $20/mo",
        "price": 2000,
        "metadata": {"zes_tier": "operator"},
        "features": [
            "Everything in Scout",
            "AI phone receptionist (24/7)",
            "4 booking types",
            "AI invoicing + payments",
            "Customer memory",
            "4 social posts/month",
            "SMS reminders",
        ],
    },
    {
        "name": "ZES Autopilot",
        "description": "SEO, analytics, competitor monitoring — $30/mo",
        "price": 3000,
        "metadata": {"zes_tier": "autopilot"},
        "features": [
            "Everything in Operator",
            "Monthly SEO audit",
            "Website self-editing",
            "BI dashboard",
            "Autonomous rescheduling",
            "Competitor monitoring",
            "Trust badge",
            "Monthly strategy call",
        ],
    },
]

for p in products:
    product = stripe.Product.create(
        name=p["name"],
        description=p["description"],
        metadata=p["metadata"],
        marketing_features=[{"name": f} for f in p["features"]],
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=p["price"],
        currency="usd",
        recurring={"interval": "month"},
        metadata=p["metadata"],
    )
    print(f"Created {p['name']}: product={product.id}, price={price.id}")
```

---

# 9. MAIN.PY REGISTRATION

```python
# Add to src/main.py after existing router registrations:

from src.api.routes.zes_routes import router as zes_router
app.include_router(zes_router)  # Router #31: /api/zes
```

---

# 10. DEPLOYMENT CHECKLIST

```bash
# 1. Apply Supabase migration
psql $DATABASE_URL < supabase/migrations/20260215_zes_complete.sql

# 2. Create Stripe products
python tools/zes_stripe_setup.py

# 3. Set environment variables
export TWILIO_ACCOUNT_SID=AC...
export TWILIO_AUTH_TOKEN=...
export TWILIO_FROM_NUMBER=+18325551234

# 4. Register route in main.py (Router #31)
# 5. Build frontend: npm run build
# 6. Deploy via GitLab CI: git push origin main
# 7. Create Metabase dashboards (6 admin + 1 tenant embed)
# 8. Create n8n workflows (weekly report, review request)
# 9. Add NATS subjects to registry
# 10. Walk into 10 barbershops in Aldine with your phone
```

---

*Blueprint v1.0 — Citadel Nexus Inc. — February 15, 2026*
*SRS: ZES-BLUEPRINT-001 | CGRF: ZES-MASTER-001*
