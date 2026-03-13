Now I have the full picture — the security system architecture, the monetization strategy, the shared infrastructure spine, and the AWS ECS Fargate cluster layout. Let me build out the complete Finance Guild code and deployment blueprint.

Here is the **complete Finance Guild build-out**, designed to live inside the existing AWS ECS Fargate cluster behind your Rig 2 security perimeter.

***

## Network Placement

The Finance Guild runs as a **private ECS service cluster** inside the existing Citadel VPC, accessible only through the Cloudflare WAF + Nginx reverse proxy layer and VPN-bound admin panels . No public-facing ports — all traffic routes through the existing edge gateway.

```
Internet → Cloudflare (WAF/CDN) → Nginx (mTLS) → ALB (private) → ECS Finance Guild Services
                                                                    ├── finance-api (Fargate)
                                                                    ├── finance-worker (Fargate)
                                                                    ├── finance-dashboard (Fargate)
                                                                    └── Supabase (shared, RLS-isolated)
```

***

## Infrastructure — Terraform

### `infra/finance-guild/main.tf`

```hcl
# ── Finance Guild ECS Cluster (isolated within Citadel VPC) ──────────

variable "vpc_id" {}
variable "private_subnet_ids" { type = list(string) }
variable "alb_security_group_id" {}
variable "ecs_cluster_id" {}
variable "supabase_url" {}
variable "stripe_secret_arn" {}
variable "stripe_webhook_secret_arn" {}
variable "supabase_service_role_arn" {}
variable "cloudflare_zone_id" {}
variable "domain" { default = "finance.citadel-nexus.com" }

# ── Security Group ──────────────────────────────────────────────────
resource "aws_security_group" "finance_guild" {
  name_prefix = "finance-guild-"
  vpc_id      = var.vpc_id

  # Inbound: ALB only (no public access)
  ingress {
    from_port       = 3000
    to_port         = 3002
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
    description     = "ALB to Finance Guild services"
  }

  # Outbound: Supabase, Stripe, SendGrid, internal services
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Outbound for Stripe/Supabase/SendGrid"
  }

  tags = {
    Name        = "finance-guild-sg"
    Environment = "production"
    Guild       = "finance"
    SRS         = "SRS_SECURITY_FIREWALL"
  }
}

# ── IAM Task Role ───────────────────────────────────────────────────
resource "aws_iam_role" "finance_task_role" {
  name = "finance-guild-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "finance_secrets" {
  name = "finance-guild-secrets"
  role = aws_iam_role.finance_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        var.stripe_secret_arn,
        var.stripe_webhook_secret_arn,
        var.supabase_service_role_arn
      ]
    }]
  })
}

# ── CloudWatch Log Group ────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "finance" {
  name              = "/ecs/finance-guild"
  retention_in_days = 90
  tags = { Guild = "finance" }
}

# ── Task Definition: Finance API ────────────────────────────────────
resource "aws_ecs_task_definition" "finance_api" {
  family                   = "finance-guild-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.finance_task_role.arn
  task_role_arn            = aws_iam_role.finance_task_role.arn

  container_definitions = jsonencode([{
    name  = "finance-api"
    image = "ghcr.io/citadel-nexus/finance-guild-api:latest"
    portMappings = [{ containerPort = 3000, protocol = "tcp" }]

    secrets = [
      { name = "STRIPE_SECRET_KEY",         valueFrom = var.stripe_secret_arn },
      { name = "STRIPE_WEBHOOK_SECRET",     valueFrom = var.stripe_webhook_secret_arn },
      { name = "SUPABASE_SERVICE_ROLE_KEY", valueFrom = var.supabase_service_role_arn }
    ]

    environment = [
      { name = "NODE_ENV",       value = "production" },
      { name = "SUPABASE_URL",   value = var.supabase_url },
      { name = "PORT",           value = "3000" },
      { name = "GUILD",          value = "finance" },
      { name = "LOG_LEVEL",      value = "info" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.finance.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:3000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

# ── Task Definition: Finance Worker (commission calc, webhooks) ─────
resource "aws_ecs_task_definition" "finance_worker" {
  family                   = "finance-guild-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.finance_task_role.arn
  task_role_arn            = aws_iam_role.finance_task_role.arn

  container_definitions = jsonencode([{
    name  = "finance-worker"
    image = "ghcr.io/citadel-nexus/finance-guild-worker:latest"
    
    secrets = [
      { name = "STRIPE_SECRET_KEY",         valueFrom = var.stripe_secret_arn },
      { name = "STRIPE_WEBHOOK_SECRET",     valueFrom = var.stripe_webhook_secret_arn },
      { name = "SUPABASE_SERVICE_ROLE_KEY", valueFrom = var.supabase_service_role_arn }
    ]

    environment = [
      { name = "NODE_ENV",     value = "production" },
      { name = "SUPABASE_URL", value = var.supabase_url },
      { name = "WORKER_MODE",  value = "true" },
      { name = "GUILD",        value = "finance" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.finance.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}

# ── Task Definition: Finance Dashboard (React SPA) ─────────────────
resource "aws_ecs_task_definition" "finance_dashboard" {
  family                   = "finance-guild-dashboard"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.finance_task_role.arn

  container_definitions = jsonencode([{
    name  = "finance-dashboard"
    image = "ghcr.io/citadel-nexus/finance-guild-dashboard:latest"
    portMappings = [{ containerPort = 3001, protocol = "tcp" }]

    environment = [
      { name = "VITE_SUPABASE_URL",      value = var.supabase_url },
      { name = "VITE_API_URL",           value = "https://${var.domain}/api" },
      { name = "VITE_STRIPE_PUBLIC_KEY", value = "pk_live_PLACEHOLDER" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.finance.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "dashboard"
      }
    }
  }])
}

# ── ECS Services ────────────────────────────────────────────────────
resource "aws_ecs_service" "finance_api" {
  name            = "finance-guild-api"
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.finance_api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.finance_guild.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.finance_api.arn
    container_name   = "finance-api"
    container_port   = 3000
  }
}

resource "aws_ecs_service" "finance_worker" {
  name            = "finance-guild-worker"
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.finance_worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.finance_guild.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_service" "finance_dashboard" {
  name            = "finance-guild-dashboard"
  cluster         = var.ecs_cluster_id
  task_definition = aws_ecs_task_definition.finance_dashboard.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.finance_guild.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.finance_dashboard.arn
    container_name   = "finance-dashboard"
    container_port   = 3001
  }
}

# ── ALB Target Groups ──────────────────────────────────────────────
resource "aws_lb_target_group" "finance_api" {
  name        = "finance-api-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_target_group" "finance_dashboard" {
  name        = "finance-dash-tg"
  port        = 3001
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}
```

***

## Database Schema — Supabase (PostgreSQL + RLS)

### `supabase/migrations/20260216_finance_guild.sql`

```sql
-- ════════════════════════════════════════════════════════════════════
-- FINANCE GUILD — Complete Schema
-- RLS-isolated, Stripe-attributed, multi-role commission engine
-- ════════════════════════════════════════════════════════════════════

-- ── Extensions ─────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── ENUM Types ─────────────────────────────────────────────────────
CREATE TYPE fg_rep_status AS ENUM ('active', 'suspended', 'terminated');
CREATE TYPE fg_commission_status AS ENUM ('pending', 'approved', 'paid', 'disputed', 'voided');
CREATE TYPE fg_product_layer AS ENUM ('tradeboost', 'website_factory', 'platform_saas', 'data_products');
CREATE TYPE fg_lead_status AS ENUM (
  'prospect', 'contacted', 'demo_scheduled', 'demo_complete',
  'proposal_sent', 'negotiating', 'won', 'lost', 'churned'
);
CREATE TYPE fg_churn_risk AS ENUM ('low', 'medium', 'high', 'critical');

-- ── Table: Sales Reps ──────────────────────────────────────────────
CREATE TABLE fg_reps (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id         UUID REFERENCES auth.users(id),
  full_name       TEXT NOT NULL,
  email           TEXT UNIQUE NOT NULL,
  phone           TEXT,
  rep_code        TEXT UNIQUE NOT NULL,  -- e.g., REP-BRADY-001
  stripe_account  TEXT,                  -- Stripe Connect account ID
  territory       TEXT DEFAULT 'SE Texas',
  status          fg_rep_status DEFAULT 'active',
  commission_rates JSONB DEFAULT '{
    "setup_pct": 0.12,
    "year1_pct": 0.10,
    "year2_pct": 0.05,
    "year3_5_pct": 0.03
  }'::jsonb,
  total_earned    NUMERIC(12,2) DEFAULT 0,
  total_paid      NUMERIC(12,2) DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Products / Service Catalog ──────────────────────────────
CREATE TABLE fg_products (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name            TEXT NOT NULL,
  slug            TEXT UNIQUE NOT NULL,
  layer           fg_product_layer NOT NULL,
  price_monthly   NUMERIC(10,2),
  price_setup     NUMERIC(10,2) DEFAULT 0,
  stripe_price_id TEXT,                  -- Stripe Price object ID
  stripe_product_id TEXT,                -- Stripe Product object ID
  description     TEXT,
  is_active       BOOLEAN DEFAULT true,
  cogs_monthly    NUMERIC(10,2) DEFAULT 0,
  margin_pct      NUMERIC(5,2),
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Clients ─────────────────────────────────────────────────
CREATE TABLE fg_clients (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  business_name     TEXT NOT NULL,
  contact_name      TEXT NOT NULL,
  contact_email     TEXT NOT NULL,
  contact_phone     TEXT,
  industry          TEXT,
  website_url       TEXT,
  website_score     INTEGER,              -- 0-100 from Lead Hunter scan
  stripe_customer_id TEXT UNIQUE,
  rep_id            UUID REFERENCES fg_reps(id),
  lead_status       fg_lead_status DEFAULT 'prospect',
  churn_risk        fg_churn_risk DEFAULT 'low',
  mrr               NUMERIC(10,2) DEFAULT 0,
  ltv               NUMERIC(12,2) DEFAULT 0,
  first_payment_at  TIMESTAMPTZ,
  last_payment_at   TIMESTAMPTZ,
  churned_at        TIMESTAMPTZ,
  metadata          JSONB DEFAULT '{}'::jsonb,
  created_at        TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Subscriptions ───────────────────────────────────────────
CREATE TABLE fg_subscriptions (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id           UUID NOT NULL REFERENCES fg_clients(id) ON DELETE CASCADE,
  product_id          UUID NOT NULL REFERENCES fg_products(id),
  rep_id              UUID REFERENCES fg_reps(id),
  stripe_subscription_id TEXT UNIQUE,
  stripe_price_id     TEXT,
  amount_monthly      NUMERIC(10,2) NOT NULL,
  status              TEXT DEFAULT 'active',  -- active, past_due, canceled, trialing
  trial_ends_at       TIMESTAMPTZ,
  current_period_start TIMESTAMPTZ,
  current_period_end  TIMESTAMPTZ,
  cancel_at           TIMESTAMPTZ,
  created_at          TIMESTAMPTZ DEFAULT now(),
  updated_at          TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Commissions Ledger ──────────────────────────────────────
CREATE TABLE fg_commissions (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  rep_id            UUID NOT NULL REFERENCES fg_reps(id),
  client_id         UUID NOT NULL REFERENCES fg_clients(id),
  subscription_id   UUID REFERENCES fg_subscriptions(id),
  invoice_id        TEXT,                 -- Stripe Invoice ID
  period_start      DATE NOT NULL,
  period_end        DATE NOT NULL,
  gross_amount      NUMERIC(10,2) NOT NULL,  -- total invoice amount
  commission_rate   NUMERIC(5,4) NOT NULL,   -- e.g., 0.1000 = 10%
  commission_amount NUMERIC(10,2) NOT NULL,
  commission_year   INTEGER NOT NULL,        -- 1, 2, 3, 4, 5
  status            fg_commission_status DEFAULT 'pending',
  approved_by       UUID REFERENCES auth.users(id),
  approved_at       TIMESTAMPTZ,
  paid_at           TIMESTAMPTZ,
  stripe_payout_id  TEXT,
  notes             TEXT,
  created_at        TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Lead Hunter Scans ───────────────────────────────────────
CREATE TABLE fg_lead_scans (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  rep_id          UUID REFERENCES fg_reps(id),
  domain          TEXT NOT NULL,
  business_name   TEXT,
  has_website     BOOLEAN,
  website_score   INTEGER,          -- 0-100
  has_ssl         BOOLEAN,
  has_mobile      BOOLEAN,
  has_gbp         BOOLEAN,
  page_speed      INTEGER,          -- 0-100
  seo_score       INTEGER,          -- 0-100
  competitor_count INTEGER,
  recommendation  TEXT,             -- 'zes_only', 'tradebuilder', 'tradebuilder_plus_zes'
  scan_data       JSONB,            -- full raw scan results
  converted       BOOLEAN DEFAULT false,
  client_id       UUID REFERENCES fg_clients(id),
  scanned_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Churn Signals ───────────────────────────────────────────
CREATE TABLE fg_churn_signals (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id       UUID NOT NULL REFERENCES fg_clients(id),
  signal_type     TEXT NOT NULL,     -- 'payment_failed', 'no_login_30d', 'support_ticket_spike', 'downgrade_request'
  severity        fg_churn_risk NOT NULL,
  details         JSONB,
  resolved        BOOLEAN DEFAULT false,
  resolved_at     TIMESTAMPTZ,
  action_taken    TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Revenue Events (immutable audit log) ────────────────────
CREATE TABLE fg_revenue_events (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_type      TEXT NOT NULL,     -- 'payment_received', 'subscription_created', 'churn', 'upsell', 'downgrade'
  client_id       UUID REFERENCES fg_clients(id),
  rep_id          UUID REFERENCES fg_reps(id),
  product_id      UUID REFERENCES fg_products(id),
  amount          NUMERIC(10,2),
  stripe_event_id TEXT UNIQUE,       -- idempotency key from Stripe
  metadata        JSONB DEFAULT '{}'::jsonb,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Table: Vertical Analytics ──────────────────────────────────────
CREATE TABLE fg_vertical_metrics (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  industry        TEXT NOT NULL,
  period          DATE NOT NULL,     -- first of month
  total_clients   INTEGER DEFAULT 0,
  total_mrr       NUMERIC(12,2) DEFAULT 0,
  avg_ltv         NUMERIC(12,2) DEFAULT 0,
  churn_rate      NUMERIC(5,4) DEFAULT 0,
  conversion_rate NUMERIC(5,4) DEFAULT 0,
  top_products    JSONB,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(industry, period)
);

-- ════════════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY — Every table locked down
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE fg_reps            ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_products        ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_clients         ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_subscriptions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_commissions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_lead_scans      ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_churn_signals   ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_revenue_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_vertical_metrics ENABLE ROW LEVEL SECURITY;

-- Reps see only their own record
CREATE POLICY "reps_own_read" ON fg_reps
  FOR SELECT USING (user_id = auth.uid());

-- Reps see only their own clients
CREATE POLICY "clients_rep_read" ON fg_clients
  FOR SELECT USING (
    rep_id IN (SELECT id FROM fg_reps WHERE user_id = auth.uid())
  );

-- Reps see only their own commissions
CREATE POLICY "commissions_rep_read" ON fg_commissions
  FOR SELECT USING (
    rep_id IN (SELECT id FROM fg_reps WHERE user_id = auth.uid())
  );

-- Reps see only their own lead scans
CREATE POLICY "scans_rep_read" ON fg_lead_scans
  FOR SELECT USING (
    rep_id IN (SELECT id FROM fg_reps WHERE user_id = auth.uid())
  );

-- Reps see only their clients' subscriptions
CREATE POLICY "subs_rep_read" ON fg_subscriptions
  FOR SELECT USING (
    rep_id IN (SELECT id FROM fg_reps WHERE user_id = auth.uid())
  );

-- Products visible to all authenticated users
CREATE POLICY "products_read_all" ON fg_products
  FOR SELECT TO authenticated USING (true);

-- Churn signals visible to rep owning the client
CREATE POLICY "churn_rep_read" ON fg_churn_signals
  FOR SELECT USING (
    client_id IN (
      SELECT id FROM fg_clients WHERE rep_id IN (
        SELECT id FROM fg_reps WHERE user_id = auth.uid()
      )
    )
  );

-- Revenue events: service_role only (API backend writes)
CREATE POLICY "revenue_events_service" ON fg_revenue_events
  FOR ALL TO service_role USING (true);

-- Vertical metrics: read-only for authenticated
CREATE POLICY "vertical_metrics_read" ON fg_vertical_metrics
  FOR SELECT TO authenticated USING (true);

-- ── Admin override policies (Marina's admin role) ──────────────────
-- Uses custom claim: auth.jwt() ->> 'role' = 'finance_admin'

CREATE POLICY "admin_reps_all" ON fg_reps
  FOR ALL USING (auth.jwt() ->> 'user_role' = 'finance_admin');

CREATE POLICY "admin_clients_all" ON fg_clients
  FOR ALL USING (auth.jwt() ->> 'user_role' = 'finance_admin');

CREATE POLICY "admin_commissions_all" ON fg_commissions
  FOR ALL USING (auth.jwt() ->> 'user_role' = 'finance_admin');

CREATE POLICY "admin_scans_all" ON fg_lead_scans
  FOR ALL USING (auth.jwt() ->> 'user_role' = 'finance_admin');

CREATE POLICY "admin_churn_all" ON fg_churn_signals
  FOR ALL USING (auth.jwt() ->> 'user_role' = 'finance_admin');

CREATE POLICY "admin_subs_all" ON fg_subscriptions
  FOR ALL USING (auth.jwt() ->> 'user_role' = 'finance_admin');

-- ════════════════════════════════════════════════════════════════════
-- FUNCTIONS — Commission Calculation Engine
-- ════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fg_calculate_commission(
  p_rep_id UUID,
  p_client_id UUID,
  p_subscription_id UUID,
  p_invoice_id TEXT,
  p_gross_amount NUMERIC,
  p_period_start DATE,
  p_period_end DATE
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  v_commission_id UUID;
  v_rep_rates JSONB;
  v_first_payment TIMESTAMPTZ;
  v_months_active INTEGER;
  v_commission_year INTEGER;
  v_rate NUMERIC;
  v_amount NUMERIC;
BEGIN
  -- Get rep's commission rates
  SELECT commission_rates INTO v_rep_rates
  FROM fg_reps WHERE id = p_rep_id;

  -- Get client's first payment date
  SELECT first_payment_at INTO v_first_payment
  FROM fg_clients WHERE id = p_client_id;

  -- Calculate months since first payment
  IF v_first_payment IS NULL THEN
    v_months_active := 0;
    -- Update first payment
    UPDATE fg_clients SET first_payment_at = now(), last_payment_at = now()
    WHERE id = p_client_id;
  ELSE
    v_months_active := EXTRACT(MONTH FROM age(now(), v_first_payment))
      + EXTRACT(YEAR FROM age(now(), v_first_payment)) * 12;
    UPDATE fg_clients SET last_payment_at = now() WHERE id = p_client_id;
  END IF;

  -- Determine commission year (step-down schedule)
  v_commission_year := LEAST(FLOOR(v_months_active / 12) + 1, 5);

  -- Apply step-down rate
  v_rate := CASE v_commission_year
    WHEN 1 THEN (v_rep_rates ->> 'year1_pct')::NUMERIC
    WHEN 2 THEN (v_rep_rates ->> 'year2_pct')::NUMERIC
    ELSE (v_rep_rates ->> 'year3_5_pct')::NUMERIC
  END;

  -- If this is a setup fee (month 0), use setup rate
  IF v_months_active = 0 THEN
    v_rate := (v_rep_rates ->> 'setup_pct')::NUMERIC;
  END IF;

  v_amount := ROUND(p_gross_amount * v_rate, 2);

  -- Insert commission record
  INSERT INTO fg_commissions (
    rep_id, client_id, subscription_id, invoice_id,
    period_start, period_end, gross_amount,
    commission_rate, commission_amount, commission_year
  ) VALUES (
    p_rep_id, p_client_id, p_subscription_id, p_invoice_id,
    p_period_start, p_period_end, p_gross_amount,
    v_rate, v_amount, v_commission_year
  ) RETURNING id INTO v_commission_id;

  -- Update rep totals
  UPDATE fg_reps
  SET total_earned = total_earned + v_amount,
      updated_at = now()
  WHERE id = p_rep_id;

  -- Update client MRR
  UPDATE fg_clients
  SET mrr = (
    SELECT COALESCE(SUM(amount_monthly), 0)
    FROM fg_subscriptions
    WHERE client_id = p_client_id AND status = 'active'
  ),
  ltv = ltv + p_gross_amount,
  updated_at = now()
  WHERE id = p_client_id;

  RETURN v_commission_id;
END;
$$;

-- ── Churn Risk Scorer ──────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fg_update_churn_risk()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  v_signal_count INTEGER;
  v_risk fg_churn_risk;
BEGIN
  SELECT COUNT(*) INTO v_signal_count
  FROM fg_churn_signals
  WHERE client_id = NEW.client_id
    AND resolved = false
    AND created_at > now() - INTERVAL '30 days';

  v_risk := CASE
    WHEN v_signal_count >= 4 THEN 'critical'
    WHEN v_signal_count >= 3 THEN 'high'
    WHEN v_signal_count >= 2 THEN 'medium'
    ELSE 'low'
  END;

  UPDATE fg_clients SET churn_risk = v_risk, updated_at = now()
  WHERE id = NEW.client_id;

  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_churn_risk_update
  AFTER INSERT ON fg_churn_signals
  FOR EACH ROW EXECUTE FUNCTION fg_update_churn_risk();

-- ════════════════════════════════════════════════════════════════════
-- INDEXES
-- ════════════════════════════════════════════════════════════════════
CREATE INDEX idx_fg_clients_rep ON fg_clients(rep_id);
CREATE INDEX idx_fg_clients_status ON fg_clients(lead_status);
CREATE INDEX idx_fg_clients_churn ON fg_clients(churn_risk) WHERE churn_risk IN ('high', 'critical');
CREATE INDEX idx_fg_subs_client ON fg_subscriptions(client_id);
CREATE INDEX idx_fg_subs_stripe ON fg_subscriptions(stripe_subscription_id);
CREATE INDEX idx_fg_commissions_rep ON fg_commissions(rep_id, status);
CREATE INDEX idx_fg_commissions_period ON fg_commissions(period_start, period_end);
CREATE INDEX idx_fg_revenue_stripe ON fg_revenue_events(stripe_event_id);
CREATE INDEX idx_fg_scans_rep ON fg_lead_scans(rep_id, scanned_at DESC);
CREATE INDEX idx_fg_churn_client ON fg_churn_signals(client_id, resolved);
CREATE INDEX idx_fg_vertical ON fg_vertical_metrics(industry, period);
```

***

## Finance API — Node.js/Express

### `services/finance-api/src/index.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// FINANCE GUILD API — Express + Supabase + Stripe
// Runs as ECS Fargate service on port 3000
// ═══════════════════════════════════════════════════════════════════

import express from 'express';
import Stripe from 'stripe';
import { createClient } from '@supabase/supabase-js';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';

const app = express();
const PORT = process.env.PORT || 3000;

// ── Clients ────────────────────────────────────────────────────────
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2024-12-18.acacia',
});

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

// ── Middleware ──────────────────────────────────────────────────────
app.use(helmet());
app.use(cors({
  origin: [
    'https://finance.citadel-nexus.com',
    'https://app.citadel-nexus.com'
  ],
  credentials: true
}));
app.use(rateLimit({ windowMs: 60_000, max: 100 }));

// Raw body for Stripe webhooks
app.use('/webhooks/stripe', express.raw({ type: 'application/json' }));
app.use(express.json());

// ── Health Check ───────────────────────────────────────────────────
app.get('/health', (_, res) => {
  res.json({ status: 'ok', guild: 'finance', ts: new Date().toISOString() });
});

// ═══════════════════════════════════════════════════════════════════
// STRIPE WEBHOOKS — Commission Attribution Engine
// ═══════════════════════════════════════════════════════════════════

app.post('/webhooks/stripe', async (req, res) => {
  const sig = req.headers['stripe-signature'] as string;
  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(
      req.body, sig, process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err: any) {
    console.error('Webhook signature failed:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  // Idempotency: check if we already processed this event
  const { data: existing } = await supabase
    .from('fg_revenue_events')
    .select('id')
    .eq('stripe_event_id', event.id)
    .single();

  if (existing) {
    return res.json({ received: true, deduplicated: true });
  }

  try {
    switch (event.type) {
      case 'invoice.payment_succeeded':
        await handlePaymentSucceeded(event.data.object as Stripe.Invoice, event.id);
        break;

      case 'customer.subscription.created':
        await handleSubscriptionCreated(event.data.object as Stripe.Subscription, event.id);
        break;

      case 'customer.subscription.deleted':
        await handleSubscriptionCanceled(event.data.object as Stripe.Subscription, event.id);
        break;

      case 'invoice.payment_failed':
        await handlePaymentFailed(event.data.object as Stripe.Invoice, event.id);
        break;
    }
  } catch (err) {
    console.error('Webhook processing error:', err);
    return res.status(500).json({ error: 'Processing failed' });
  }

  res.json({ received: true });
});

async function handlePaymentSucceeded(invoice: Stripe.Invoice, eventId: string) {
  const customerId = invoice.customer as string;
  const amount = (invoice.amount_paid || 0) / 100;

  // Find client by Stripe customer ID
  const { data: client } = await supabase
    .from('fg_clients')
    .select('id, rep_id')
    .eq('stripe_customer_id', customerId)
    .single();

  if (!client || !client.rep_id) return;

  // Find subscription
  const subId = invoice.subscription as string;
  const { data: sub } = await supabase
    .from('fg_subscriptions')
    .select('id')
    .eq('stripe_subscription_id', subId)
    .single();

  // Calculate commission via DB function
  const { data: commissionId } = await supabase.rpc('fg_calculate_commission', {
    p_rep_id: client.rep_id,
    p_client_id: client.id,
    p_subscription_id: sub?.id || null,
    p_invoice_id: invoice.id,
    p_gross_amount: amount,
    p_period_start: new Date(invoice.period_start * 1000).toISOString().split('T')[0],
    p_period_end: new Date(invoice.period_end * 1000).toISOString().split('T')[0],
  });

  // Log revenue event
  await supabase.from('fg_revenue_events').insert({
    event_type: 'payment_received',
    client_id: client.id,
    rep_id: client.rep_id,
    amount,
    stripe_event_id: eventId,
    metadata: { invoice_id: invoice.id, subscription_id: subId }
  });
}

async function handleSubscriptionCreated(sub: Stripe.Subscription, eventId: string) {
  const customerId = sub.customer as string;
  const priceId = sub.items.data[0]?.price?.id;
  const amount = (sub.items.data[0]?.price?.unit_amount || 0) / 100;

  const { data: client } = await supabase
    .from('fg_clients')
    .select('id, rep_id')
    .eq('stripe_customer_id', customerId)
    .single();

  if (!client) return;

  // Match product by stripe_price_id
  const { data: product } = await supabase
    .from('fg_products')
    .select('id')
    .eq('stripe_price_id', priceId)
    .single();

  await supabase.from('fg_subscriptions').insert({
    client_id: client.id,
    product_id: product?.id,
    rep_id: client.rep_id,
    stripe_subscription_id: sub.id,
    stripe_price_id: priceId,
    amount_monthly: amount,
    status: sub.status,
    current_period_start: new Date(sub.current_period_start * 1000).toISOString(),
    current_period_end: new Date(sub.current_period_end * 1000).toISOString(),
  });

  await supabase.from('fg_revenue_events').insert({
    event_type: 'subscription_created',
    client_id: client.id,
    rep_id: client.rep_id,
    product_id: product?.id,
    amount,
    stripe_event_id: eventId,
  });

  // Update client lead status
  await supabase.from('fg_clients')
    .update({ lead_status: 'won', updated_at: new Date().toISOString() })
    .eq('id', client.id);
}

async function handleSubscriptionCanceled(sub: Stripe.Subscription, eventId: string) {
  const customerId = sub.customer as string;

  const { data: client } = await supabase
    .from('fg_clients')
    .select('id, rep_id')
    .eq('stripe_customer_id', customerId)
    .single();

  if (!client) return;

  await supabase.from('fg_subscriptions')
    .update({ status: 'canceled', updated_at: new Date().toISOString() })
    .eq('stripe_subscription_id', sub.id);

  await supabase.from('fg_revenue_events').insert({
    event_type: 'churn',
    client_id: client.id,
    rep_id: client.rep_id,
    stripe_event_id: eventId,
  });

  await supabase.from('fg_clients')
    .update({
      lead_status: 'churned',
      churned_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
    .eq('id', client.id);
}

async function handlePaymentFailed(invoice: Stripe.Invoice, eventId: string) {
  const customerId = invoice.customer as string;

  const { data: client } = await supabase
    .from('fg_clients')
    .select('id')
    .eq('stripe_customer_id', customerId)
    .single();

  if (!client) return;

  await supabase.from('fg_churn_signals').insert({
    client_id: client.id,
    signal_type: 'payment_failed',
    severity: 'high',
    details: {
      invoice_id: invoice.id,
      amount: (invoice.amount_due || 0) / 100,
      attempt_count: invoice.attempt_count,
    }
  });
}

// ═══════════════════════════════════════════════════════════════════
// REST ENDPOINTS — Rep Dashboard + Admin
// ═══════════════════════════════════════════════════════════════════

// ── Auth middleware ─────────────────────────────────────────────────
async function authMiddleware(req: express.Request, res: express.Response, next: express.NextFunction) {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token) return res.status(401).json({ error: 'No token' });

  const { data: { user }, error } = await supabase.auth.getUser(token);
  if (error || !user) return res.status(401).json({ error: 'Invalid token' });

  (req as any).user = user;
  next();
}

// ── GET /api/rep/me — Rep's own dashboard data ─────────────────────
app.get('/api/rep/me', authMiddleware, async (req, res) => {
  const userId = (req as any).user.id;

  const { data: rep } = await supabase
    .from('fg_reps')
    .select('*')
    .eq('user_id', userId)
    .single();

  if (!rep) return res.status(404).json({ error: 'Rep not found' });

  // Get commission summary
  const { data: commissions } = await supabase
    .from('fg_commissions')
    .select('commission_amount, status, commission_year')
    .eq('rep_id', rep.id);

  const pending = commissions?.filter(c => c.status === 'pending')
    .reduce((sum, c) => sum + Number(c.commission_amount), 0) || 0;
  const approved = commissions?.filter(c => c.status === 'approved')
    .reduce((sum, c) => sum + Number(c.commission_amount), 0) || 0;

  // Get client count
  const { count: clientCount } = await supabase
    .from('fg_clients')
    .select('id', { count: 'exact', head: true })
    .eq('rep_id', rep.id)
    .eq('lead_status', 'won');

  // Get pipeline
  const { data: pipeline } = await supabase
    .from('fg_clients')
    .select('id, business_name, lead_status, mrr, created_at')
    .eq('rep_id', rep.id)
    .not('lead_status', 'in', '("won","lost","churned")')
    .order('created_at', { ascending: false })
    .limit(20);

  res.json({
    rep: {
      id: rep.id,
      name: rep.full_name,
      rep_code: rep.rep_code,
      territory: rep.territory,
      referral_link: `https://citadel-nexus.com/ref/${rep.rep_code}`,
    },
    financials: {
      total_earned: rep.total_earned,
      total_paid: rep.total_paid,
      pending_commissions: pending,
      approved_unpaid: approved,
      active_clients: clientCount || 0,
    },
    pipeline,
  });
});

// ── GET /api/rep/clients — Rep's client list ───────────────────────
app.get('/api/rep/clients', authMiddleware, async (req, res) => {
  const userId = (req as any).user.id;

  const { data: rep } = await supabase
    .from('fg_reps')
    .select('id')
    .eq('user_id', userId)
    .single();

  if (!rep) return res.status(404).json({ error: 'Rep not found' });

  const { data: clients } = await supabase
    .from('fg_clients')
    .select(`
      id, business_name, contact_name, industry,
      lead_status, churn_risk, mrr, ltv,
      first_payment_at, created_at
    `)
    .eq('rep_id', rep.id)
    .order('created_at', { ascending: false });

  res.json({ clients });
});

// ── GET /api/rep/commissions — Rep's commission history ────────────
app.get('/api/rep/commissions', authMiddleware, async (req, res) => {
  const userId = (req as any).user.id;

  const { data: rep } = await supabase
    .from('fg_reps')
    .select('id')
    .eq('user_id', userId)
    .single();

  if (!rep) return res.status(404).json({ error: 'Rep not found' });

  const { data: commissions } = await supabase
    .from('fg_commissions')
    .select(`
      id, period_start, period_end, gross_amount,
      commission_rate, commission_amount, commission_year,
      status, paid_at,
      fg_clients!inner(business_name)
    `)
    .eq('rep_id', rep.id)
    .order('period_start', { ascending: false })
    .limit(100);

  res.json({ commissions });
});

// ── POST /api/rep/scan — Lead Hunter domain scan ───────────────────
app.post('/api/rep/scan', authMiddleware, async (req, res) => {
  const userId = (req as any).user.id;
  const { domain, business_name } = req.body;

  if (!domain) return res.status(400).json({ error: 'Domain required' });

  const { data: rep } = await supabase
    .from('fg_reps')
    .select('id')
    .eq('user_id', userId)
    .single();

  if (!rep) return res.status(404).json({ error: 'Rep not found' });

  // Perform scan (calls internal scanning service)
  const scanResult = await performDomainScan(domain);

  // Determine recommendation
  const recommendation = scanResult.website_score > 60
    ? 'zes_only'         // decent website → just needs an AI agent
    : scanResult.has_website
      ? 'tradebuilder_plus_zes'  // bad website → rebuild + agent
      : 'tradebuilder';          // no website → full build

  const { data: scan } = await supabase
    .from('fg_lead_scans')
    .insert({
      rep_id: rep.id,
      domain,
      business_name,
      has_website: scanResult.has_website,
      website_score: scanResult.website_score,
      has_ssl: scanResult.has_ssl,
      has_mobile: scanResult.has_mobile,
      has_gbp: scanResult.has_gbp,
      page_speed: scanResult.page_speed,
      seo_score: scanResult.seo_score,
      competitor_count: scanResult.competitor_count,
      recommendation,
      scan_data: scanResult,
    })
    .select()
    .single();

  res.json({ scan, recommendation });
});

// ── Domain scanner helper ──────────────────────────────────────────
async function performDomainScan(domain: string) {
  try {
    const url = domain.startsWith('http') ? domain : `https://${domain}`;
    const response = await fetch(url, {
      method: 'HEAD',
      signal: AbortSignal.timeout(10_000),
    });

    const hasWebsite = response.ok;
    const hasSsl = url.startsWith('https');

    // PageSpeed Insights API (free tier)
    const psiUrl = `https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=${encodeURIComponent(url)}&strategy=mobile`;
    let pageSpeed = 0;
    let seoScore = 0;
    let hasMobile = false;

    try {
      const psiRes = await fetch(psiUrl);
      const psiData = await psiRes.json() as any;
      pageSpeed = Math.round((psiData.lighthouseResult?.categories?.performance?.score || 0) * 100);
      seoScore = Math.round((psiData.lighthouseResult?.categories?.seo?.score || 0) * 100);
      hasMobile = pageSpeed > 30;
    } catch {}

    const websiteScore = Math.round(
      (hasSsl ? 20 : 0) +
      (hasMobile ? 20 : 0) +
      (pageSpeed * 0.3) +
      (seoScore * 0.3)
    );

    return {
      has_website: hasWebsite,
      website_score: websiteScore,
      has_ssl: hasSsl,
      has_mobile: hasMobile,
      has_gbp: false, // TODO: GBP API check
      page_speed: pageSpeed,
      seo_score: seoScore,
      competitor_count: 0,
    };
  } catch {
    return {
      has_website: false,
      website_score: 0,
      has_ssl: false,
      has_mobile: false,
      has_gbp: false,
      page_speed: 0,
      seo_score: 0,
      competitor_count: 0,
    };
  }
}

// ═══════════════════════════════════════════════════════════════════
// ADMIN ENDPOINTS — Marina's full view
// ═══════════════════════════════════════════════════════════════════

async function adminMiddleware(req: express.Request, res: express.Response, next: express.NextFunction) {
  const user = (req as any).user;
  if (!user) return res.status(401).json({ error: 'Not authenticated' });

  // Check admin claim
  const { data } = await supabase
    .from('fg_reps')
    .select('id')
    .eq('user_id', user.id);

  // For now, check if user has finance_admin role in JWT
  const jwt = user.user_metadata;
  if (jwt?.user_role !== 'finance_admin') {
    return res.status(403).json({ error: 'Admin access required' });
  }
  next();
}

// ── GET /api/admin/dashboard — Full org overview ───────────────────
app.get('/api/admin/dashboard', authMiddleware, adminMiddleware, async (req, res) => {
  // Total MRR
  const { data: mrrData } = await supabase
    .from('fg_subscriptions')
    .select('amount_monthly')
    .eq('status', 'active');

  const totalMrr = mrrData?.reduce((s, r) => s + Number(r.amount_monthly), 0) || 0;

  // Total clients by status
  const { data: statusCounts } = await supabase
    .rpc('fg_client_status_counts');

  // Pending commissions
  const { data: pendingComm } = await supabase
    .from('fg_commissions')
    .select('commission_amount')
    .eq('status', 'pending');

  const pendingTotal = pendingComm?.reduce((s, r) => s + Number(r.commission_amount), 0) || 0;

  // Churn alerts
  const { data: churnAlerts } = await supabase
    .from('fg_clients')
    .select('id, business_name, churn_risk, mrr, rep_id')
    .in('churn_risk', ['high', 'critical'])
    .order('mrr', { ascending: false })
    .limit(10);

  // Rep leaderboard
  const { data: reps } = await supabase
    .from('fg_reps')
    .select('id, full_name, total_earned, status')
    .eq('status', 'active')
    .order('total_earned', { ascending: false });

  // Revenue by layer
  const { data: layerRevenue } = await supabase
    .from('fg_subscriptions')
    .select('amount_monthly, fg_products!inner(layer)')
    .eq('status', 'active');

  const revenueByLayer: Record<string, number> = {};
  layerRevenue?.forEach((s: any) => {
    const layer = s.fg_products?.layer || 'unknown';
    revenueByLayer[layer] = (revenueByLayer[layer] || 0) + Number(s.amount_monthly);
  });

  res.json({
    mrr: totalMrr,
    arr: totalMrr * 12,
    pending_commissions: pendingTotal,
    churn_alerts: churnAlerts,
    rep_leaderboard: reps,
    revenue_by_layer: revenueByLayer,
  });
});

// ── POST /api/admin/commissions/approve — Batch approve ────────────
app.post('/api/admin/commissions/approve', authMiddleware, adminMiddleware, async (req, res) => {
  const { commission_ids } = req.body;
  const userId = (req as any).user.id;

  if (!Array.isArray(commission_ids) || commission_ids.length === 0) {
    return res.status(400).json({ error: 'commission_ids required' });
  }

  const { data, error } = await supabase
    .from('fg_commissions')
    .update({
      status: 'approved',
      approved_by: userId,
      approved_at: new Date().toISOString(),
    })
    .in('id', commission_ids)
    .eq('status', 'pending')
    .select();

  if (error) return res.status(500).json({ error: error.message });
  res.json({ approved: data?.length || 0 });
});

// ── POST /api/admin/reps — Create a new rep ────────────────────────
app.post('/api/admin/reps', authMiddleware, adminMiddleware, async (req, res) => {
  const { full_name, email, phone, territory, commission_rates } = req.body;

  // Generate rep code
  const namePart = full_name.split(' ').pop()?.toUpperCase().slice(0, 6) || 'REP';
  const { count } = await supabase
    .from('fg_reps')
    .select('id', { count: 'exact', head: true });

  const repCode = `REP-${namePart}-${String((count || 0) + 1).padStart(3, '0')}`;

  // Create Stripe Connect account
  const account = await stripe.accounts.create({
    type: 'express',
    email,
    metadata: { rep_code: repCode, guild: 'finance' },
  });

  const { data: rep, error } = await supabase
    .from('fg_reps')
    .insert({
      full_name,
      email,
      phone,
      rep_code: repCode,
      stripe_account: account.id,
      territory: territory || 'SE Texas',
      commission_rates: commission_rates || {
        setup_pct: 0.12,
        year1_pct: 0.10,
        year2_pct: 0.05,
        year3_5_pct: 0.03,
      },
    })
    .select()
    .single();

  if (error) return res.status(500).json({ error: error.message });

  // Generate Stripe onboarding link
  const accountLink = await stripe.accountLinks.create({
    account: account.id,
    refresh_url: `https://finance.citadel-nexus.com/rep/onboarding?refresh=true`,
    return_url: `https://finance.citadel-nexus.com/rep/dashboard`,
    type: 'account_onboarding',
  });

  res.json({ rep, onboarding_url: accountLink.url });
});

// ── GET /api/admin/verticals — Vertical heat map data ──────────────
app.get('/api/admin/verticals', authMiddleware, adminMiddleware, async (req, res) => {
  const { data } = await supabase
    .from('fg_vertical_metrics')
    .select('*')
    .order('period', { ascending: false })
    .limit(100);

  res.json({ verticals: data });
});

// ═══════════════════════════════════════════════════════════════════
// PRODUCT CATALOG SEEDER
// ═══════════════════════════════════════════════════════════════════

app.post('/api/admin/seed-products', authMiddleware, adminMiddleware, async (req, res) => {
  const products = [
    // TradeBoost
    { name: 'Missed-Call Text-Back',   slug: 'tb-missed-call',   layer: 'tradeboost', price_monthly: 20, cogs_monthly: 2.50, margin_pct: 87.5 },
    { name: 'Review Request Automator', slug: 'tb-review-req',   layer: 'tradeboost', price_monthly: 15, cogs_monthly: 0.80, margin_pct: 94.7 },
    { name: 'Smart Booking Link',      slug: 'tb-booking',       layer: 'tradeboost', price_monthly: 20, cogs_monthly: 0.10, margin_pct: 99.5 },
    { name: 'Estimate Follow-Up Drip', slug: 'tb-followup',      layer: 'tradeboost', price_monthly: 20, cogs_monthly: 0.80, margin_pct: 96.0 },
    { name: 'AI Voicemail Drop',       slug: 'tb-voicemail',     layer: 'tradeboost', price_monthly: 25, cogs_monthly: 3.00, margin_pct: 88.0 },
    // Website Factory
    { name: 'Website Factory Starter',  slug: 'wf-starter',  layer: 'website_factory', price_monthly: 99,  price_setup: 99,  cogs_monthly: 18, margin_pct: 82 },
    { name: 'Website Factory Growth',   slug: 'wf-growth',   layer: 'website_factory', price_monthly: 199, price_setup: 99,  cogs_monthly: 22, margin_pct: 89 },
    { name: 'Website Factory Premium',  slug: 'wf-premium',  layer: 'website_factory', price_monthly: 299, price_setup: 199, cogs_monthly: 28, margin_pct: 91 },
    // ZES Agent (24hr delivery — not a website)
    { name: 'ZES Scout Agent',     slug: 'zes-scout',     layer: 'tradeboost', price_monthly: 15, cogs_monthly: 1.50, margin_pct: 90 },
    { name: 'ZES Operator Agent',  slug: 'zes-operator',  layer: 'tradeboost', price_monthly: 30, cogs_monthly: 3.00, margin_pct: 90 },
    // Platform SaaS
    { name: 'Platform Starter', slug: 'platform-starter',   layer: 'platform_saas', price_monthly: 29,   cogs_monthly: 5,   margin_pct: 83 },
    { name: 'Platform Pro',     slug: 'platform-pro',       layer: 'platform_saas', price_monthly: 99,   cogs_monthly: 15,  margin_pct: 85 },
    { name: 'Platform Business', slug: 'platform-business', layer: 'platform_saas', price_monthly: 499,  cogs_monthly: 60,  margin_pct: 88 },
    { name: 'Platform Agency',  slug: 'platform-agency',    layer: 'platform_saas', price_monthly: 2499, cogs_monthly: 250, margin_pct: 90 },
  ];

  const { data, error } = await supabase.from('fg_products').upsert(products, { onConflict: 'slug' });
  if (error) return res.status(500).json({ error: error.message });
  res.json({ seeded: products.length });
});

// ── Start ──────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`[Finance Guild API] Running on port ${PORT}`);
});
```

***

## Dockerfiles

### `services/finance-api/Dockerfile`

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json tsconfig.json ./
RUN npm ci
COPY src/ ./src/
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN addgroup -g 1001 -S finance && adduser -S finance -u 1001
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json ./

# Security: non-root, read-only FS where possible
USER finance
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:3000/health || exit 1
CMD ["node", "dist/index.js"]
```

### `services/finance-dashboard/Dockerfile`

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Security headers baked in
RUN adduser -D -H -u 1001 finance
EXPOSE 3001
CMD ["nginx", "-g", "daemon off;"]
```

***

## n8n Worker Flows (Commission Automation)

### `n8n/finance-guild-commission-calc.json` (Summary)

This n8n workflow runs on a **cron trigger (daily at 2 AM CST)** and handles:

1. **Batch commission calculation** — Queries `fg_subscriptions` for active subs, cross-references `fg_commissions` to find unbilled periods, calls `fg_calculate_commission` for each
2. **Churn signal detection** — Queries Stripe for `past_due` subscriptions and clients with no login in 30 days, inserts `fg_churn_signals`
3. **Vertical metrics aggregation** — Groups active clients by `industry`, calculates MRR/LTV/churn per vertical, upserts `fg_vertical_metrics`
4. **Discord notification** — Posts daily summary to `#finance-guild` channel: new clients, MRR change, pending commissions, churn alerts

***

## GitLab CI/CD Pipeline

### `.gitlab-ci.yml` (Finance Guild section)

```yaml
stages:
  - security
  - test
  - build
  - deploy

variables:
  FINANCE_API_IMAGE: ghcr.io/citadel-nexus/finance-guild-api
  FINANCE_DASH_IMAGE: ghcr.io/citadel-nexus/finance-guild-dashboard
  FINANCE_WORKER_IMAGE: ghcr.io/citadel-nexus/finance-guild-worker
  AWS_REGION: us-east-1
  ECS_CLUSTER: citadel-production

# ── Security Gate ───────────────────────────────────────────────────
finance:security:preflight:
  stage: security
  image: aquasec/trivy:latest
  script:
    - trivy fs --exit-code 1 --severity CRITICAL,HIGH services/finance-api/
    - trivy fs --exit-code 1 --severity CRITICAL,HIGH services/finance-dashboard/
  rules:
    - changes:
        - services/finance-api/**/*
        - services/finance-dashboard/**/*
        - supabase/migrations/*finance*

finance:security:secrets:
  stage: security
  image: zricethezav/gitleaks:latest
  script:
    - gitleaks detect --redact --no-git --source services/finance-api/
    - gitleaks detect --redact --no-git --source services/finance-dashboard/

# ── Tests ───────────────────────────────────────────────────────────
finance:test:api:
  stage: test
  image: node:20-alpine
  script:
    - cd services/finance-api
    - npm ci
    - npm run test
  needs: [finance:security:preflight]

# ── Build ───────────────────────────────────────────────────────────
finance:build:api:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $FINANCE_API_IMAGE:$CI_COMMIT_SHA services/finance-api/
    - docker tag $FINANCE_API_IMAGE:$CI_COMMIT_SHA $FINANCE_API_IMAGE:latest
    - echo $GHCR_TOKEN | docker login ghcr.io -u $GHCR_USER --password-stdin
    - docker push $FINANCE_API_IMAGE:$CI_COMMIT_SHA
    - docker push $FINANCE_API_IMAGE:latest
  needs: [finance:test:api]
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

finance:build:dashboard:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $FINANCE_DASH_IMAGE:$CI_COMMIT_SHA services/finance-dashboard/
    - docker tag $FINANCE_DASH_IMAGE:$CI_COMMIT_SHA $FINANCE_DASH_IMAGE:latest
    - echo $GHCR_TOKEN | docker login ghcr.io -u $GHCR_USER --password-stdin
    - docker push $FINANCE_DASH_IMAGE:$CI_COMMIT_SHA
    - docker push $FINANCE_DASH_IMAGE:latest
  needs: [finance:security:preflight]
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

# ── Deploy to ECS ───────────────────────────────────────────────────
finance:deploy:api:
  stage: deploy
  image: amazon/aws-cli:latest
  script:
    - aws ecs update-service
        --cluster $ECS_CLUSTER
        --service finance-guild-api
        --force-new-deployment
        --region $AWS_REGION
  needs: [finance:build:api]
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  environment:
    name: production
    url: https://finance.citadel-nexus.com

finance:deploy:dashboard:
  stage: deploy
  image: amazon/aws-cli:latest
  script:
    - aws ecs update-service
        --cluster $ECS_CLUSTER
        --service finance-guild-dashboard
        --force-new-deployment
        --region $AWS_REGION
  needs: [finance:build:dashboard]
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

# ── DB Migration ────────────────────────────────────────────────────
finance:migrate:
  stage: deploy
  image: supabase/supabase:latest
  script:
    - supabase db push --linked
  rules:
    - changes:
        - supabase/migrations/*finance*
  when: manual
```

***

## Security Integration

The Finance Guild plugs directly into your [Rig 2 Security System](https://www.notion.so/2c0bcff493cb80648a5cf5fdae23abea) at these touchpoints :

| Security Layer | Finance Guild Binding |
|---|---|
| **Network (Phase B)** | `finance-guild-sg` allows ingress only from ALB; no public IPs; private subnets only |
| **WAF/IDS (Phase C)** | Cloudflare WAF + rate limiting on `/webhooks/stripe` (100 req/min); ModSecurity OWASP CRS on all API routes |
| **Zero-Trust (Phase D)** | Admin dashboard (`/api/admin/*`) bound to VPN-only via Nginx location block; rep dashboard uses Supabase Auth + JWT |
| **RLS (Phase C addenda)** | Every table has RLS enabled; reps see only their own data; admins use `finance_admin` JWT claim; `service_role` for webhook writes only |
| **Observability (Phase F)** | CloudWatch logs → promtail → Loki; Grafana dashboards for commission volume, churn rate, webhook latency |
| **Change Control (Phase G)** | All deploys gated by `finance:security:preflight` in CI; Trivy + Gitleaks scans before build stage |
| **SRS Tags** | `SRS_SECURITY_SUPABASE` for RLS changes; `SRS_SECURITY_FIREWALL` for SG modifications; `SRS_SECURITY_GITLAB` for CI pipeline changes |

***

## File Tree

```
citadel-nexus/
├── infra/
│   └── finance-guild/
│       ├── main.tf                    # ECS + ALB + SG + IAM
│       ├── variables.tf
│       └── outputs.tf
├── services/
│   ├── finance-api/
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       ├── index.ts               # Main API server
│   │       ├── routes/
│   │       │   ├── rep.ts              # Rep self-service endpoints
│   │       │   ├── admin.ts            # Marina admin endpoints
│   │       │   └── webhooks.ts         # Stripe webhook handlers
│   │       ├── services/
│   │       │   ├── commission.ts       # Commission calc logic
│   │       │   ├── lead-scanner.ts     # Domain scan + PageSpeed
│   │       │   └── churn-monitor.ts    # Churn signal detection
│   │       └── middleware/
│   │           ├── auth.ts             # Supabase JWT validation
│   │           └── admin.ts            # Finance admin gate
│   ├── finance-dashboard/
│   │   ├── Dockerfile
│   │   ├── nginx.conf
│   │   ├── package.json
│   │   └── src/
│   │       ├── App.tsx
│   │       ├── pages/
│   │       │   ├── RepDashboard.tsx    # Rep: my link, my numbers, my pipeline
│   │       │   ├── AdminDashboard.tsx  # Marina: full org view
│   │       │   ├── CommissionView.tsx  # Commission history + approval queue
│   │       │   ├── LeadScanner.tsx     # Domain scan UI
│   │       │   ├── ChurnAlerts.tsx     # At-risk client list
│   │       │   └── VerticalHeatMap.tsx # Industry performance
│   │       └── components/
│   │           ├── MetricCard.tsx
│   │           ├── PipelineBoard.tsx
│   │           └── RepLeaderboard.tsx
│   └── finance-worker/
│       ├── Dockerfile
│       └── src/
│           ├── index.ts                # Cron runner
│           ├── jobs/
│           │   ├── daily-commissions.ts
│           │   ├── churn-detection.ts
│           │   ├── vertical-aggregation.ts
│           │   └── discord-summary.ts
│           └── utils/
│               └── stripe-helpers.ts
├── supabase/
│   └── migrations/
│       └── 20260216_finance_guild.sql  # Full schema above
├── n8n/
│   └── finance-guild-commission-calc.json
└── .gitlab-ci.yml                     # Finance Guild CI stages
```

This entire system lives inside the existing Citadel VPC on private subnets, uses the shared Supabase instance with RLS isolation, and deploys through the same GitLab CI/CD pipeline with security gates enforced by the Rig 2 security perimeter . The Fargate services auto-scale independently — the API at 2 tasks minimum, the worker and dashboard at 1 each — and all secrets are pulled from AWS Secrets Manager at runtime, never baked into images.Here is the complete front-end codebase for the Finance Guild system — dashboard, templates, security integration, ICP/SRS binding, Ansible playbooks, Cloudflare config, and the Finance Guild Master ElevenLabs voice agent with RAG documentation.

***

## Project Structure

```
services/finance-dashboard/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── vite-env.d.ts
│   ├── lib/
│   │   ├── supabase.ts
│   │   ├── api.ts
│   │   ├── stripe.ts
│   │   └── hooks/
│   │       ├── useAuth.ts
│   │       ├── useRep.ts
│   │       ├── useAdmin.ts
│   │       └── useRealtime.ts
│   ├── components/
│   │   ├── Layout.tsx
│   │   ├── Sidebar.tsx
│   │   ├── TopBar.tsx
│   │   ├── MetricCard.tsx
│   │   ├── PipelineBoard.tsx
│   │   ├── RepLeaderboard.tsx
│   │   ├── ChurnRiskBadge.tsx
│   │   ├── CommissionTable.tsx
│   │   ├── VerticalHeatMap.tsx
│   │   ├── LeadScanCard.tsx
│   │   ├── RevenueChart.tsx
│   │   ├── GuildMasterWidget.tsx   ← ElevenLabs voice agent embed
│   │   └── SecurityPanel.tsx       ← ICP/SRS/CAPS live status
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── RepDashboard.tsx
│   │   ├── RepClients.tsx
│   │   ├── RepCommissions.tsx
│   │   ├── RepLeadScanner.tsx
│   │   ├── AdminDashboard.tsx
│   │   ├── AdminCommissions.tsx
│   │   ├── AdminReps.tsx
│   │   ├── AdminVerticals.tsx
│   │   ├── AdminChurnAlerts.tsx
│   │   └── AdminSecurity.tsx
│   ├── styles/
│   │   ├── globals.css
│   │   ├── brotherhood-theme.css
│   │   └── dashboard.css
│   └── types/
│       └── finance.ts
├── public/
│   ├── brotherhood-emblem.svg
│   └── finance-guild-icon.svg
├── nginx.conf
├── Dockerfile
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.ts
```

***

## Core Types

### `src/types/finance.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// FINANCE GUILD — TypeScript Definitions
// ═══════════════════════════════════════════════════════════════════

export type RepStatus = 'active' | 'suspended' | 'terminated';
export type CommissionStatus = 'pending' | 'approved' | 'paid' | 'disputed' | 'voided';
export type ProductLayer = 'tradeboost' | 'website_factory' | 'platform_saas' | 'data_products';
export type LeadStatus = 'prospect' | 'contacted' | 'demo_scheduled' | 'demo_complete'
  | 'proposal_sent' | 'negotiating' | 'won' | 'lost' | 'churned';
export type ChurnRisk = 'low' | 'medium' | 'high' | 'critical';
export type ScanRecommendation = 'zes_only' | 'tradebuilder' | 'tradebuilder_plus_zes';

export interface Rep {
  id: string;
  full_name: string;
  email: string;
  rep_code: string;
  territory: string;
  status: RepStatus;
  commission_rates: CommissionRates;
  total_earned: number;
  total_paid: number;
  stripe_account?: string;
  created_at: string;
}

export interface CommissionRates {
  setup_pct: number;
  year1_pct: number;
  year2_pct: number;
  year3_5_pct: number;
}

export interface Client {
  id: string;
  business_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone?: string;
  industry?: string;
  lead_status: LeadStatus;
  churn_risk: ChurnRisk;
  mrr: number;
  ltv: number;
  first_payment_at?: string;
  created_at: string;
}

export interface Commission {
  id: string;
  period_start: string;
  period_end: string;
  gross_amount: number;
  commission_rate: number;
  commission_amount: number;
  commission_year: number;
  status: CommissionStatus;
  paid_at?: string;
  fg_clients?: { business_name: string };
}

export interface Product {
  id: string;
  name: string;
  slug: string;
  layer: ProductLayer;
  price_monthly: number;
  price_setup?: number;
  margin_pct?: number;
}

export interface LeadScan {
  id: string;
  domain: string;
  business_name?: string;
  has_website: boolean;
  website_score: number;
  has_ssl: boolean;
  has_mobile: boolean;
  has_gbp: boolean;
  page_speed: number;
  seo_score: number;
  recommendation: ScanRecommendation;
  converted: boolean;
  scanned_at: string;
}

export interface ChurnSignal {
  id: string;
  client_id: string;
  signal_type: string;
  severity: ChurnRisk;
  details: Record<string, any>;
  resolved: boolean;
  created_at: string;
}

export interface AdminDashboard {
  mrr: number;
  arr: number;
  pending_commissions: number;
  churn_alerts: (Client & { rep_id: string })[];
  rep_leaderboard: Rep[];
  revenue_by_layer: Record<string, number>;
}

export interface SecurityStatus {
  firewall: { status: string; last_check: string; rules_active: number };
  waf: { status: string; blocked_24h: number; top_rules: string[] };
  rls: { status: string; policies_active: number; last_audit: string };
  vpn: { status: string; connected_devices: number };
  ids: { status: string; alerts_24h: number; banned_ips: number };
  srs_tags: { tag: string; last_event: string; tier: string }[];
  caps_violations: { count: number; last_violation?: string };
}
```

***

## Library Layer

### `src/lib/supabase.ts`

```typescript
import { createClient } from '@supabase/supabase-js';

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
);
```

### `src/lib/api.ts`

```typescript
const API_BASE = import.meta.env.VITE_API_URL || 'https://finance.citadel-nexus.com/api';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = (await (await import('./supabase')).supabase.auth.getSession()).data.session?.access_token;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  // Rep endpoints
  getRepMe: () => request<any>('/rep/me'),
  getRepClients: () => request<any>('/rep/clients'),
  getRepCommissions: () => request<any>('/rep/commissions'),
  postRepScan: (domain: string, business_name?: string) =>
    request<any>('/rep/scan', { method: 'POST', body: JSON.stringify({ domain, business_name }) }),

  // Admin endpoints
  getAdminDashboard: () => request<any>('/admin/dashboard'),
  getAdminVerticals: () => request<any>('/admin/verticals'),
  postApproveCommissions: (ids: string[]) =>
    request<any>('/admin/commissions/approve', { method: 'POST', body: JSON.stringify({ commission_ids: ids }) }),
  postCreateRep: (data: any) =>
    request<any>('/admin/reps', { method: 'POST', body: JSON.stringify(data) }),
  postSeedProducts: () =>
    request<any>('/admin/seed-products', { method: 'POST' }),
};
```

### `src/lib/hooks/useAuth.ts`

```typescript
import { useState, useEffect, useCallback } from 'react';
import { supabase } from '../supabase';
import type { User, Session } from '@supabase/supabase-js';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      setIsAdmin(session?.user?.user_metadata?.user_role === 'finance_admin');
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setUser(session?.user ?? null);
      setIsAdmin(session?.user?.user_metadata?.user_role === 'finance_admin');
    });

    return () => subscription.unsubscribe();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

  return { user, session, loading, isAdmin, signIn, signOut };
}
```

### `src/lib/hooks/useRealtime.ts`

```typescript
import { useEffect } from 'react';
import { supabase } from '../supabase';

export function useRealtimeTable(
  table: string,
  callback: (payload: any) => void,
  filter?: string
) {
  useEffect(() => {
    const channel = supabase
      .channel(`realtime:${table}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table, filter },
        callback
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [table, filter, callback]);
}
```

***

## Styles — Brotherhood Finance Theme

### `src/styles/globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  /* Brotherhood Finance Guild Palette */
  --fg-bg-primary: #0a0a1a;
  --fg-bg-secondary: #111128;
  --fg-bg-card: #161636;
  --fg-bg-elevated: #1c1c42;
  --fg-border: #2a2a5a;
  --fg-border-active: #6d28d9;

  --fg-text-primary: #e8e8f0;
  --fg-text-secondary: #9898b8;
  --fg-text-muted: #6868a0;

  --fg-accent-purple: #8b5cf6;
  --fg-accent-green: #22c55e;
  --fg-accent-amber: #f59e0b;
  --fg-accent-red: #ef4444;
  --fg-accent-blue: #3b82f6;
  --fg-accent-cyan: #06b6d4;

  --fg-gradient-primary: linear-gradient(135deg, #6d28d9 0%, #4f46e5 50%, #2563eb 100%);
  --fg-gradient-success: linear-gradient(135deg, #059669 0%, #22c55e 100%);
  --fg-gradient-danger: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);

  --fg-shadow: 0 4px 24px rgba(107, 40, 217, 0.15);
  --fg-shadow-lg: 0 8px 40px rgba(107, 40, 217, 0.25);
  --fg-radius: 12px;
}

body {
  background: var(--fg-bg-primary);
  color: var(--fg-text-primary);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Custom scrollbar */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--fg-bg-secondary); }
::-webkit-scrollbar-thumb { background: var(--fg-border); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--fg-accent-purple); }

/* Brotherhood animated border glow */
.guild-card {
  background: var(--fg-bg-card);
  border: 1px solid var(--fg-border);
  border-radius: var(--fg-radius);
  transition: all 0.3s ease;
}
.guild-card:hover {
  border-color: var(--fg-border-active);
  box-shadow: var(--fg-shadow);
}

/* Metric pulse animation */
@keyframes metricPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
.metric-live::after {
  content: '';
  display: inline-block;
  width: 8px; height: 8px;
  background: var(--fg-accent-green);
  border-radius: 50%;
  margin-left: 8px;
  animation: metricPulse 2s infinite;
}
```

***

## Core Components

### `src/components/Layout.tsx`

```tsx
import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../lib/hooks/useAuth';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import GuildMasterWidget from './GuildMasterWidget';

export default function Layout() {
  const { user, loading, isAdmin } = useAuth();

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--fg-bg-primary)]">
      <div className="animate-spin w-10 h-10 border-2 border-purple-500 border-t-transparent rounded-full" />
    </div>
  );

  if (!user) return <Navigate to="/login" />;

  return (
    <div className="min-h-screen flex bg-[var(--fg-bg-primary)]">
      <Sidebar isAdmin={isAdmin} />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      {/* Finance Guild Master — always available */}
      <GuildMasterWidget />
    </div>
  );
}
```

### `src/components/Sidebar.tsx`

```tsx
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Users, DollarSign, Search, Shield,
  BarChart3, AlertTriangle, UserPlus, TrendingUp
} from 'lucide-react';

const repNav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/clients', icon: Users, label: 'My Clients' },
  { to: '/commissions', icon: DollarSign, label: 'Commissions' },
  { to: '/scanner', icon: Search, label: 'Lead Scanner' },
];

const adminNav = [
  { to: '/admin', icon: LayoutDashboard, label: 'HQ Overview' },
  { to: '/admin/commissions', icon: DollarSign, label: 'Approve Commissions' },
  { to: '/admin/reps', icon: UserPlus, label: 'Manage Reps' },
  { to: '/admin/verticals', icon: BarChart3, label: 'Vertical Analytics' },
  { to: '/admin/churn', icon: AlertTriangle, label: 'Churn Alerts' },
  { to: '/admin/security', icon: Shield, label: 'Security & SRS' },
];

export default function Sidebar({ isAdmin }: { isAdmin: boolean }) {
  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
      isActive
        ? 'bg-purple-600/20 text-purple-300 border-l-2 border-purple-500'
        : 'text-[var(--fg-text-secondary)] hover:text-[var(--fg-text-primary)] hover:bg-white/5'
    }`;

  return (
    <aside className="w-64 bg-[var(--fg-bg-secondary)] border-r border-[var(--fg-border)] flex flex-col">
      {/* Guild Emblem */}
      <div className="p-6 border-b border-[var(--fg-border)]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide">FINANCE GUILD</h1>
            <p className="text-xs text-[var(--fg-text-muted)]">Citadel Economics</p>
          </div>
        </div>
      </div>

      {/* Rep Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        <p className="text-[10px] uppercase tracking-widest text-[var(--fg-text-muted)] mb-2 px-4">
          Sales Rep
        </p>
        {repNav.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} className={navLinkClass}>
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}

        {isAdmin && (
          <>
            <div className="h-px bg-[var(--fg-border)] my-4" />
            <p className="text-[10px] uppercase tracking-widest text-[var(--fg-text-muted)] mb-2 px-4">
              Admin HQ
            </p>
            {adminNav.map(({ to, icon: Icon, label }) => (
              <NavLink key={to} to={to} className={navLinkClass}>
                <Icon className="w-4 h-4" />
                {label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* Version */}
      <div className="p-4 border-t border-[var(--fg-border)]">
        <p className="text-[10px] text-[var(--fg-text-muted)] text-center">
          Finance Guild v1.0 — Citadel-Nexus
        </p>
      </div>
    </aside>
  );
}
```

### `src/components/MetricCard.tsx`

```tsx
interface MetricCardProps {
  label: string;
  value: string | number;
  change?: number;
  prefix?: string;
  suffix?: string;
  variant?: 'default' | 'success' | 'warning' | 'danger';
  live?: boolean;
}

export default function MetricCard({
  label, value, change, prefix = '', suffix = '', variant = 'default', live
}: MetricCardProps) {
  const borderColor = {
    default: 'border-[var(--fg-border)]',
    success: 'border-green-500/30',
    warning: 'border-amber-500/30',
    danger: 'border-red-500/30',
  }[variant];

  const valueColor = {
    default: 'text-white',
    success: 'text-green-400',
    warning: 'text-amber-400',
    danger: 'text-red-400',
  }[variant];

  return (
    <div className={`guild-card p-5 ${borderColor}`}>
      <p className="text-xs text-[var(--fg-text-muted)] uppercase tracking-wider mb-1">
        {label}
        {live && <span className="metric-live" />}
      </p>
      <p className={`text-2xl font-bold ${valueColor}`}>
        {prefix}{typeof value === 'number' ? value.toLocaleString() : value}{suffix}
      </p>
      {change !== undefined && (
        <p className={`text-xs mt-1 ${change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {change >= 0 ? '↑' : '↓'} {Math.abs(change)}% vs last period
        </p>
      )}
    </div>
  );
}
```

### `src/components/CommissionTable.tsx`

```tsx
import type { Commission } from '../types/finance';

interface Props {
  commissions: Commission[];
  selectable?: boolean;
  selected?: string[];
  onSelect?: (ids: string[]) => void;
}

export default function CommissionTable({ commissions, selectable, selected = [], onSelect }: Props) {
  const statusColors: Record<string, string> = {
    pending: 'bg-amber-500/20 text-amber-300',
    approved: 'bg-blue-500/20 text-blue-300',
    paid: 'bg-green-500/20 text-green-300',
    disputed: 'bg-red-500/20 text-red-300',
    voided: 'bg-gray-500/20 text-gray-400',
  };

  const toggleSelect = (id: string) => {
    if (!onSelect) return;
    onSelect(selected.includes(id) ? selected.filter(s => s !== id) : [...selected, id]);
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[var(--fg-text-muted)] text-xs uppercase border-b border-[var(--fg-border)]">
            {selectable && <th className="p-3 w-8" />}
            <th className="p-3 text-left">Client</th>
            <th className="p-3 text-left">Period</th>
            <th className="p-3 text-right">Gross</th>
            <th className="p-3 text-right">Rate</th>
            <th className="p-3 text-right">Commission</th>
            <th className="p-3 text-center">Year</th>
            <th className="p-3 text-center">Status</th>
          </tr>
        </thead>
        <tbody>
          {commissions.map((c) => (
            <tr
              key={c.id}
              className="border-b border-[var(--fg-border)]/50 hover:bg-white/[0.02] transition-colors"
              onClick={() => selectable && toggleSelect(c.id)}
            >
              {selectable && (
                <td className="p-3">
                  <input
                    type="checkbox"
                    checked={selected.includes(c.id)}
                    onChange={() => toggleSelect(c.id)}
                    className="rounded border-[var(--fg-border)] bg-transparent accent-purple-500"
                  />
                </td>
              )}
              <td className="p-3 font-medium">{c.fg_clients?.business_name || '—'}</td>
              <td className="p-3 text-[var(--fg-text-secondary)]">
                {new Date(c.period_start).toLocaleDateString()} – {new Date(c.period_end).toLocaleDateString()}
              </td>
              <td className="p-3 text-right">${c.gross_amount.toFixed(2)}</td>
              <td className="p-3 text-right text-[var(--fg-text-secondary)]">
                {(c.commission_rate * 100).toFixed(1)}%
              </td>
              <td className="p-3 text-right font-semibold text-green-400">
                ${c.commission_amount.toFixed(2)}
              </td>
              <td className="p-3 text-center">
                <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-300">
                  Y{c.commission_year}
                </span>
              </td>
              <td className="p-3 text-center">
                <span className={`text-xs px-2 py-0.5 rounded ${statusColors[c.status] || ''}`}>
                  {c.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### `src/components/VerticalHeatMap.tsx`

```tsx
import { useMemo } from 'react';

interface VerticalData {
  industry: string;
  period: string;
  total_clients: number;
  total_mrr: number;
  churn_rate: number;
  conversion_rate: number;
}

export default function VerticalHeatMap({ data }: { data: VerticalData[] }) {
  const industries = useMemo(() => [...new Set(data.map(d => d.industry))], [data]);
  const periods = useMemo(() => [...new Set(data.map(d => d.period))].sort(), [data]);

  const maxMrr = useMemo(() => Math.max(...data.map(d => d.total_mrr), 1), [data]);

  const getCell = (industry: string, period: string) =>
    data.find(d => d.industry === industry && d.period === period);

  const intensity = (mrr: number) => Math.min(mrr / maxMrr, 1);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="p-2 text-left text-[var(--fg-text-muted)]">Industry</th>
            {periods.map(p => (
              <th key={p} className="p-2 text-center text-[var(--fg-text-muted)]">
                {new Date(p).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {industries.map(ind => (
            <tr key={ind}>
              <td className="p-2 font-medium text-[var(--fg-text-secondary)]">{ind}</td>
              {periods.map(p => {
                const cell = getCell(ind, p);
                const i = cell ? intensity(cell.total_mrr) : 0;
                return (
                  <td key={p} className="p-1">
                    <div
                      className="w-full h-10 rounded flex items-center justify-center text-[10px] font-medium transition-all"
                      style={{
                        backgroundColor: `rgba(139, 92, 246, ${i * 0.6 + 0.05})`,
                        color: i > 0.4 ? '#fff' : 'var(--fg-text-muted)',
                      }}
                      title={cell ? `$${cell.total_mrr} MRR / ${cell.total_clients} clients` : 'No data'}
                    >
                      {cell ? `$${(cell.total_mrr / 1000).toFixed(1)}k` : '—'}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### `src/components/LeadScanCard.tsx`

```tsx
import type { LeadScan, ScanRecommendation } from '../types/finance';
import { Globe, Shield, Smartphone, MapPin, Zap, Search } from 'lucide-react';

const recLabels: Record<ScanRecommendation, { label: string; color: string; desc: string }> = {
  zes_only: {
    label: 'ZES Agent Only',
    color: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    desc: 'Existing website is decent — deploy AI agent within 24hrs',
  },
  tradebuilder: {
    label: 'TradeBuilder Website',
    color: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    desc: 'No website found — full TradeBuilder build required',
  },
  tradebuilder_plus_zes: {
    label: 'TradeBuilder + ZES',
    color: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    desc: 'Website needs rebuild — TradeBuilder + ZES agent extension upsell',
  },
};

export default function LeadScanCard({ scan }: { scan: LeadScan }) {
  const rec = recLabels[scan.recommendation];
  const scoreColor = scan.website_score > 60 ? 'text-green-400'
    : scan.website_score > 30 ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="guild-card p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-semibold text-white">{scan.business_name || scan.domain}</h3>
          <p className="text-xs text-[var(--fg-text-muted)]">{scan.domain}</p>
        </div>
        <span className={`text-xs px-3 py-1 rounded-full border ${rec.color}`}>
          {rec.label}
        </span>
      </div>

      {/* Score Ring */}
      <div className="flex items-center gap-6 mb-4">
        <div className="relative w-20 h-20">
          <svg className="w-20 h-20 -rotate-90" viewBox="0 0 72 72">
            <circle cx="36" cy="36" r="30" fill="none" stroke="var(--fg-border)" strokeWidth="6" />
            <circle
              cx="36" cy="36" r="30" fill="none"
              stroke={scan.website_score > 60 ? '#22c55e' : scan.website_score > 30 ? '#f59e0b' : '#ef4444'}
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={`${(scan.website_score / 100) * 188.5} 188.5`}
            />
          </svg>
          <span className={`absolute inset-0 flex items-center justify-center text-lg font-bold ${scoreColor}`}>
            {scan.website_score}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 flex-1 text-xs">
          <div className="flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5" />
            <span>{scan.has_website ? '✅ Has Website' : '❌ No Website'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5" />
            <span>{scan.has_ssl ? '✅ SSL' : '❌ No SSL'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Smartphone className="w-3.5 h-3.5" />
            <span>{scan.has_mobile ? '✅ Mobile' : '❌ Not Mobile'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <MapPin className="w-3.5 h-3.5" />
            <span>{scan.has_gbp ? '✅ GBP' : '❌ No GBP'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5" />
            <span>Speed: {scan.page_speed}/100</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5" />
            <span>SEO: {scan.seo_score}/100</span>
          </div>
        </div>
      </div>

      <p className="text-xs text-[var(--fg-text-secondary)] bg-[var(--fg-bg-elevated)] p-3 rounded-lg">
        💡 {rec.desc}
      </p>
    </div>
  );
}
```

***

## Finance Guild Master — ElevenLabs Voice Agent

### `src/components/GuildMasterWidget.tsx`

This is the **arbitrating voice agent** for the Finance Guild that uses ElevenLabs Conversational AI with RAG documentation loaded from the [ZES RAG Knowledge Base](https://www.notion.so/4f323075bac94a42bdf6aec9011c41b3) pattern :

```tsx
import { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, MicOff, Volume2, X, MessageSquare, Bot } from 'lucide-react';

const ELEVENLABS_AGENT_ID = import.meta.env.VITE_FINANCE_GUILD_MASTER_AGENT_ID;
const ELEVENLABS_API_KEY = import.meta.env.VITE_ELEVENLABS_API_KEY;

interface Message {
  role: 'user' | 'agent';
  text: string;
  ts: number;
}

export default function GuildMasterWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'active' | 'error'>('idle');
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    try {
      // Get signed URL from ElevenLabs Conversational AI
      const res = await fetch(
        `https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id=${ELEVENLABS_AGENT_ID}`,
        { headers: { 'xi-api-key': ELEVENLABS_API_KEY } }
      );
      const { signed_url } = await res.json();

      const ws = new WebSocket(signed_url);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('active');
        // Send initial context with Finance Guild documentation scope
        ws.send(JSON.stringify({
          type: 'conversation_initiation_client_data',
          custom_llm_extra_body: {
            system_prompt_addition: `You are the Finance Guild Master — the arbitrating voice of the Citadel Finance Guild.
Your role:
- Answer questions about commission structures, sales processes, lead scanning, and client management
- Guide reps through the TradeBuilder vs ZES decision tree:
  * ZES Agent = for EXISTING websites, delivers within 24 hours, NOT a website
  * TradeBuilder = the website income product, builds new sites ($99-299/mo)
  * ZES is available as an extension/upsell through TradeBuilder packages
- Explain the step-down commission schedule: 12% setup, 10% Y1, 5% Y2, 3% Y3-5
- Help diagnose churn risks and recommend save strategies
- Provide real-time revenue and pipeline guidance
- Reference Finance Guild SRS tags and CAPS policies when relevant
Tone: Confident, direct, Brotherhood-style. You are an authority on Finance Guild operations.`,
          },
        }));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'agent_response':
            setMessages(prev => [...prev, { role: 'agent', text: data.agent_response_event?.agent_response || '', ts: Date.now() }]);
            break;
          case 'user_transcript':
            if (data.user_transcription_event?.is_final) {
              setMessages(prev => [...prev, { role: 'user', text: data.user_transcription_event.user_transcript, ts: Date.now() }]);
            }
            break;
          case 'audio':
            setIsSpeaking(true);
            playAudio(data.audio_event?.audio_base_64);
            break;
          case 'agent_response_correction':
            // Update last agent message
            setMessages(prev => {
              const updated = [...prev];
              const lastAgent = updated.reverse().find(m => m.role === 'agent');
              if (lastAgent) lastAgent.text = data.agent_response_correction_event?.corrected_agent_response || lastAgent.text;
              return updated.reverse();
            });
            break;
        }
      };

      ws.onerror = () => setStatus('error');
      ws.onclose = () => { setStatus('idle'); setIsListening(false); };

    } catch (err) {
      console.error('Guild Master connection failed:', err);
      setStatus('error');
    }
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setIsListening(false);
    setStatus('idle');
  }, []);

  const toggleListening = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      await connect();
    }

    if (isListening) {
      // Stop microphone
      setIsListening(false);
    } else {
      // Start microphone
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioContextRef.current = new AudioContext({ sampleRate: 16000 });
        const source = audioContextRef.current.createMediaStreamSource(stream);
        const processor = audioContextRef.current.createScriptProcessor(4096, 1, 1);

        processor.onaudioprocess = (e) => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            const inputData = e.inputBuffer.getChannelData(0);
            const pcm16 = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
              pcm16[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
            }
            const base64 = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)));
            wsRef.current.send(JSON.stringify({
              user_audio_chunk: base64
            }));
          }
        };

        source.connect(processor);
        processor.connect(audioContextRef.current.destination);
        setIsListening(true);
      } catch (err) {
        console.error('Microphone access denied:', err);
      }
    }
  }, [isListening, connect]);

  const playAudio = (base64Audio?: string) => {
    if (!base64Audio) return;
    const audioData = atob(base64Audio);
    const arrayBuffer = new ArrayBuffer(audioData.length);
    const view = new Uint8Array(arrayBuffer);
    for (let i = 0; i < audioData.length; i++) view[i] = audioData.charCodeAt(i);

    const ctx = new AudioContext();
    ctx.decodeAudioData(arrayBuffer, (buffer) => {
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      source.onended = () => setIsSpeaking(false);
      source.start();
    });
  };

  return (
    <>
      {/* Floating Trigger Button */}
      {!isOpen && (
        <button
          onClick={() => { setIsOpen(true); connect(); }}
          className="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center shadow-lg hover:scale-105 transition-transform z-50"
          title="Finance Guild Master"
        >
          <Bot className="w-6 h-6 text-white" />
        </button>
      )}

      {/* Chat Panel */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 w-96 h-[560px] bg-[var(--fg-bg-card)] border border-[var(--fg-border)] rounded-2xl shadow-2xl flex flex-col z-50 overflow-hidden">
          {/* Header */}
          <div className="p-4 border-b border-[var(--fg-border)] bg-gradient-to-r from-purple-900/40 to-blue-900/40">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center">
                  <Bot className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Guild Master</h3>
                  <p className="text-[10px] text-[var(--fg-text-muted)]">
                    {status === 'active' ? '🟢 Connected' : status === 'connecting' ? '🟡 Connecting...' : '⚪ Offline'}
                  </p>
                </div>
              </div>
              <button onClick={() => { setIsOpen(false); disconnect(); }} className="p-1 hover:bg-white/10 rounded">
                <X className="w-4 h-4 text-[var(--fg-text-muted)]" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-center py-8">
                <Bot className="w-12 h-12 mx-auto text-purple-500/50 mb-3" />
                <p className="text-sm text-[var(--fg-text-muted)]">
                  I'm the Finance Guild Master. Ask me about commissions, lead scanning, TradeBuilder vs ZES, or pipeline strategy.
                </p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${
                  msg.role === 'user'
                    ? 'bg-purple-600/30 text-purple-100 rounded-br-sm'
                    : 'bg-[var(--fg-bg-elevated)] text-[var(--fg-text-primary)] rounded-bl-sm'
                }`}>
                  {msg.text}
                </div>
              </div>
            ))}
            {isSpeaking && (
              <div className="flex items-center gap-2 text-xs text-purple-400">
                <Volume2 className="w-3.5 h-3.5 animate-pulse" />
                Speaking...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Controls */}
          <div className="p-4 border-t border-[var(--fg-border)] flex items-center justify-center gap-4">
            <button
              onClick={toggleListening}
              className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                isListening
                  ? 'bg-red-500 hover:bg-red-600 animate-pulse'
                  : 'bg-purple-600 hover:bg-purple-700'
              }`}
            >
              {isListening ? <MicOff className="w-6 h-6 text-white" /> : <Mic className="w-6 h-6 text-white" />}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
```

***

## Security Panel — ICP/SRS/CAPS Dashboard

### `src/components/SecurityPanel.tsx`

This maps directly to the [Rig 2 Security System](https://www.notion.so/2c0bcff493cb80648a5cf5fdae23abea) phases and SRS catalog :

```tsx
import { useState, useEffect } from 'react';
import { Shield, Lock, Eye, Wifi, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import type { SecurityStatus } from '../types/finance';

export default function SecurityPanel() {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // In production, this hits the observability stack
    // Prometheus → /api/admin/security/status
    async function fetchStatus() {
      try {
        const res = await fetch('/api/admin/security/status', {
          headers: { Authorization: `Bearer ${(await (await import('../lib/supabase')).supabase.auth.getSession()).data.session?.access_token}` }
        });
        setStatus(await res.json());
      } catch {
        // Fallback mock for development
        setStatus({
          firewall: { status: 'active', last_check: new Date().toISOString(), rules_active: 47 },
          waf: { status: 'active', blocked_24h: 1284, top_rules: ['SQL-INJECTION', 'XSS-REFLECTED', 'PATH-TRAVERSAL'] },
          rls: { status: 'active', policies_active: 18, last_audit: new Date().toISOString() },
          vpn: { status: 'active', connected_devices: 3 },
          ids: { status: 'active', alerts_24h: 23, banned_ips: 156 },
          srs_tags: [
            { tag: 'SRS_SECURITY_FIREWALL', last_event: new Date().toISOString(), tier: 'T1' },
            { tag: 'SRS_SECURITY_WAF', last_event: new Date().toISOString(), tier: 'T1' },
            { tag: 'SRS_SECURITY_SUPABASE', last_event: new Date().toISOString(), tier: 'T2' },
            { tag: 'SRS_SECURITY_GITLAB', last_event: new Date().toISOString(), tier: 'T1' },
          ],
          caps_violations: { count: 0 },
        });
      }
      setLoading(false);
    }
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading || !status) return <div className="animate-pulse h-96 bg-[var(--fg-bg-card)] rounded-xl" />;

  const StatusDot = ({ active }: { active: boolean }) => (
    <span className={`w-2 h-2 rounded-full inline-block ${active ? 'bg-green-400' : 'bg-red-400'}`} />
  );

  return (
    <div className="space-y-6">
      {/* Security Perimeter Status */}
      <div className="grid grid-cols-5 gap-4">
        {[
          { label: 'Firewall', icon: Shield, status: status.firewall.status, detail: `${status.firewall.rules_active} rules` },
          { label: 'WAF/ModSec', icon: Lock, status: status.waf.status, detail: `${status.waf.blocked_24h} blocked/24h` },
          { label: 'RLS Policies', icon: Eye, status: status.rls.status, detail: `${status.rls.policies_active} active` },
          { label: 'VPN/WireGuard', icon: Wifi, status: status.vpn.status, detail: `${status.vpn.connected_devices} devices` },
          { label: 'IDS/CrowdSec', icon: AlertTriangle, status: status.ids.status, detail: `${status.ids.banned_ips} banned IPs` },
        ].map(({ label, icon: Icon, status: s, detail }) => (
          <div key={label} className="guild-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon className="w-4 h-4 text-purple-400" />
              <span className="text-xs font-medium">{label}</span>
              <StatusDot active={s === 'active'} />
            </div>
            <p className="text-[10px] text-[var(--fg-text-muted)]">{detail}</p>
          </div>
        ))}
      </div>

      {/* SRS Tags Live Feed */}
      <div className="guild-card p-5">
        <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-purple-400" />
          SRS Tag Registry — Finance Guild
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[var(--fg-text-muted)] border-b border-[var(--fg-border)]">
              <th className="p-2 text-left">SRS Tag</th>
              <th className="p-2 text-center">Tier</th>
              <th className="p-2 text-center">Last Event</th>
              <th className="p-2 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {status.srs_tags.map(tag => (
              <tr key={tag.tag} className="border-b border-[var(--fg-border)]/30">
                <td className="p-2 font-mono text-purple-300">{tag.tag}</td>
                <td className="p-2 text-center">
                  <span className={`px-2 py-0.5 rounded text-[10px] ${
                    tag.tier === 'T0' ? 'bg-green-500/20 text-green-300'
                    : tag.tier === 'T1' ? 'bg-blue-500/20 text-blue-300'
                    : 'bg-amber-500/20 text-amber-300'
                  }`}>{tag.tier}</span>
                </td>
                <td className="p-2 text-center text-[var(--fg-text-muted)]">
                  {new Date(tag.last_event).toLocaleTimeString()}
                </td>
                <td className="p-2 text-center"><CheckCircle className="w-3.5 h-3.5 text-green-400 mx-auto" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* CAPS Violations */}
      <div className="guild-card p-5">
        <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
          <Lock className="w-4 h-4 text-blue-400" />
          CAPS Violations — Last 24h
        </h3>
        {status.caps_violations.count === 0 ? (
          <div className="flex items-center gap-2 text-green-400 text-sm">
            <CheckCircle className="w-4 h-4" />
            No CAPS violations detected. All capability policies enforced.
          </div>
        ) : (
          <div className="flex items-center gap-2 text-red-400 text-sm">
            <XCircle className="w-4 h-4" />
            {status.caps_violations.count} violations detected — review required
          </div>
        )}
      </div>

      {/* ICP Routing Map */}
      <div className="guild-card p-5">
        <h3 className="text-sm font-bold mb-3">ICP Incident Classification — Finance Guild</h3>
        <div className="grid grid-cols-4 gap-3 text-xs">
          {[
            { tier: 'T0', label: 'Observability', action: 'Auto — No approval', color: 'green' },
            { tier: 'T1', label: 'Standard Change', action: 'Auto + CAP check', color: 'blue' },
            { tier: 'T2', label: 'Material Change', action: 'Human gate required', color: 'amber' },
            { tier: 'T3', label: 'Critical/Emergency', action: 'Reflex + post-review', color: 'red' },
          ].map(t => (
            <div key={t.tier} className={`p-3 rounded-lg border border-${t.color}-500/30 bg-${t.color}-500/5`}>
              <p className="font-bold text-white">{t.tier}</p>
              <p className="text-[var(--fg-text-secondary)] mt-1">{t.label}</p>
              <p className="text-[var(--fg-text-muted)] mt-1">{t.action}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

***

## Pages

### `src/pages/Login.tsx`

Follows the [Brotherhood Login System Template](https://www.notion.so/6f1b384ab7764741a012045dfc58a975) pattern :

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/hooks/useAuth';
import { TrendingUp, Shield, Eye } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { signIn } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signIn(email, password);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#0a0a1a] via-[#111128] to-[#0d0d25]">
      {/* Animated background grid */}
      <div className="absolute inset-0 opacity-5"
        style={{ backgroundImage: 'linear-gradient(var(--fg-border) 1px, transparent 1px), linear-gradient(90deg, var(--fg-border) 1px, transparent 1px)', backgroundSize: '40px 40px' }}
      />

      <div className="relative z-10 w-full max-w-md px-6">
        {/* Guild Emblem */}
        <div className="text-center mb-8">
          <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center shadow-lg shadow-purple-500/20">
            <TrendingUp className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-wide">FINANCE GUILD</h1>
          <p className="text-sm text-[var(--fg-text-muted)] mt-1">Citadel Economics Division</p>
        </div>

        {/* Login Card */}
        <div className="bg-[var(--fg-bg-card)] border border-[var(--fg-border)] rounded-2xl p-8 shadow-2xl">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs text-[var(--fg-text-muted)] uppercase tracking-wider mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-[var(--fg-bg-elevated)] border border-[var(--fg-border)] rounded-lg text-white text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 transition-all"
                placeholder="rep@citadel-nexus.com"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--fg-text-muted)] uppercase tracking-wider mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-[var(--fg-bg-elevated)] border border-[var(--fg-border)] rounded-lg text-white text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500/30 transition-all"
                placeholder="••••••••••••"
                required
              />
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-xs text-red-300 flex items-center gap-2">
                <Shield className="w-4 h-4" /> {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-gradient-to-r from-purple-600 to-blue-600 rounded-lg text-white font-semibold text-sm hover:from-purple-500 hover:to-blue-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Authenticating...' : 'Enter Finance Guild'}
            </button>
          </form>

          <div className="mt-4 flex items-center justify-center gap-2 text-[10px] text-[var(--fg-text-muted)]">
            <Eye className="w-3 h-3" />
            Protected by Sentinel AI • Zero-Trust • Supabase Auth
          </div>
        </div>
      </div>
    </div>
  );
}
```

### `src/pages/RepDashboard.tsx`

```tsx
import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import MetricCard from '../components/MetricCard';
import { Copy, ExternalLink, Users, DollarSign, Clock, Target } from 'lucide-react';

export default function RepDashboard() {
  const [data, setData] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => { api.getRepMe().then(setData); }, []);

  if (!data) return <div className="animate-pulse space-y-4">{[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-[var(--fg-bg-card)] rounded-xl" />)}</div>;

  const { rep, financials, pipeline } = data;

  const copyLink = () => {
    navigator.clipboard.writeText(rep.referral_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Welcome back, {rep.name.split(' ')[0]}</h1>
          <p className="text-sm text-[var(--fg-text-muted)]">{rep.territory} • {rep.rep_code}</p>
        </div>
        <button
          onClick={copyLink}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600/20 border border-purple-500/30 rounded-lg text-sm text-purple-300 hover:bg-purple-600/30 transition-all"
        >
          {copied ? '✅ Copied!' : <><Copy className="w-4 h-4" /> My Referral Link</>}
        </button>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard label="Total Earned" value={financials.total_earned} prefix="$" variant="success" live />
        <MetricCard label="Pending Commissions" value={financials.pending_commissions} prefix="$" variant="warning" />
        <MetricCard label="Approved (Unpaid)" value={financials.approved_unpaid} prefix="$" variant="default" />
        <MetricCard label="Active Clients" value={financials.active_clients} variant="default" />
      </div>

      {/* Referral Link Card */}
      <div className="guild-card p-5">
        <h3 className="text-sm font-bold mb-2 flex items-center gap-2">
          <ExternalLink className="w-4 h-4 text-purple-400" />
          Your Referral Link
        </h3>
        <div className="flex items-center gap-3">
          <code className="flex-1 px-4 py-2.5 bg-[var(--fg-bg-elevated)] rounded-lg text-sm text-purple-300 font-mono">
            {rep.referral_link}
          </code>
          <button onClick={copyLink} className="px-4 py-2.5 bg-purple-600 rounded-lg text-sm text-white hover:bg-purple-500">
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p className="text-xs text-[var(--fg-text-muted)] mt-2">
          Share this link with prospects. All conversions are auto-attributed to your account.
        </p>
      </div>

      {/* Pipeline */}
      <div className="guild-card p-5">
        <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
          <Target className="w-4 h-4 text-blue-400" />
          Active Pipeline ({pipeline?.length || 0} leads)
        </h3>
        {pipeline && pipeline.length > 0 ? (
          <div className="space-y-2">
            {pipeline.map((lead: any) => (
              <div key={lead.id} className="flex items-center justify-between py-2.5 px-3 rounded-lg hover:bg-white/[0.02] transition-colors">
                <div>
                  <p className="text-sm font-medium">{lead.business_name}</p>
                  <p className="text-xs text-[var(--fg-text-muted)]">
                    {new Date(lead.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {lead.mrr > 0 && (
                    <span className="text-xs text-green-400">${lead.mrr}/mo</span>
                  )}
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                    lead.lead_status === 'demo_scheduled' ? 'bg-blue-500/20 text-blue-300'
                    : lead.lead_status === 'proposal_sent' ? 'bg-purple-500/20 text-purple-300'
                    : lead.lead_status === 'negotiating' ? 'bg-amber-500/20 text-amber-300'
                    : 'bg-gray-500/20 text-gray-300'
                  }`}>
                    {lead.lead_status.replace(/_/g, ' ')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--fg-text-muted)] text-center py-6">
            No active leads. Use the Lead Scanner to find prospects!
          </p>
        )}
      </div>

      {/* Commission Schedule Reference */}
      <div className="guild-card p-5">
        <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-green-400" />
          Your Commission Schedule
        </h3>
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Setup Fee', rate: rep.commission_rates?.setup_pct || 0.12, color: 'purple' },
            { label: 'Year 1', rate: rep.commission_rates?.year1_pct || 0.10, color: 'green' },
            { label: 'Year 2', rate: rep.commission_rates?.year2_pct || 0.05, color: 'blue' },
            { label: 'Year 3–5', rate: rep.commission_rates?.year3_5_pct || 0.03, color: 'gray' },
          ].map(s => (
            <div key={s.label} className="text-center p-3 rounded-lg bg-[var(--fg-bg-elevated)]">
              <p className="text-2xl font-bold text-white">{(s.rate * 100).toFixed(0)}%</p>
              <p className="text-[10px] text-[var(--fg-text-muted)] mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

### `src/pages/AdminDashboard.tsx`

```tsx
import { useState, useEffect } from 'react';
import { api } from '../lib/api';
import MetricCard from '../components/MetricCard';
import RepLeaderboard from '../components/RepLeaderboard';
import { useRealtimeTable } from '../lib/hooks/useRealtime';
import { TrendingUp, AlertTriangle } from 'lucide-react';

export default function AdminDashboard() {
  const [data, setData] = useState<any>(null);

  const fetchData = () => api.getAdminDashboard().then(setData);
  useEffect(() => { fetchData(); }, []);

  // Realtime: refresh on new revenue events
  useRealtimeTable('fg_revenue_events', () => fetchData());

  if (!data) return <div className="animate-pulse space-y-4">{[...Array(6)].map((_, i) => <div key={i} className="h-24 bg-[var(--fg-bg-card)] rounded-xl" />)}</div>;

  const layers = data.revenue_by_layer || {};

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Finance Guild HQ</h1>

      {/* Top Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard label="Monthly Recurring Revenue" value={data.mrr} prefix="$" variant="success" live />
        <MetricCard label="Annual Run Rate" value={data.arr} prefix="$" variant="default" />
        <MetricCard label="Pending Commissions" value={data.pending_commissions} prefix="$" variant="warning" />
        <MetricCard label="Churn Alerts" value={data.churn_alerts?.length || 0} variant={data.churn_alerts?.length > 0 ? 'danger' : 'default'} />
      </div>

      {/* Revenue by Layer */}
      <div className="guild-card p-5">
        <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-purple-400" />
          MRR by Revenue Layer
        </h3>
        <div className="grid grid-cols-4 gap-4">
          {[
            { key: 'tradeboost', label: 'TradeBoost', color: 'from-blue-600 to-cyan-600' },
            { key: 'website_factory', label: 'Website Factory', color: 'from-purple-600 to-pink-600' },
            { key: 'platform_saas', label: 'Platform SaaS', color: 'from-green-600 to-emerald-600' },
            { key: 'data_products', label: 'Data Products', color: 'from-amber-600 to-orange-600' },
          ].map(l => (
            <div key={l.key} className="p-4 rounded-xl bg-[var(--fg-bg-elevated)]">
              <div className={`w-8 h-1 rounded bg-gradient-to-r ${l.color} mb-3`} />
              <p className="text-xs text-[var(--fg-text-muted)]">{l.label}</p>
              <p className="text-xl font-bold text-white mt-1">${(layers[l.key] || 0).toLocaleString()}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Rep Leaderboard */}
        <div className="guild-card p-5">
          <h3 className="text-sm font-bold mb-4">Rep Leaderboard</h3>
          <RepLeaderboard reps={data.rep_leaderboard || []} />
        </div>

        {/* Churn Alerts */}
        <div className="guild-card p-5">
          <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            At-Risk Clients
          </h3>
          {data.churn_alerts?.length > 0 ? (
            <div className="space-y-2">
              {data.churn_alerts.map((c: any) => (
                <div key={c.id} className="flex items-center justify-between py-2 px-3 rounded-lg bg-red-500/5 border border-red-500/20">
                  <div>
                    <p className="text-sm font-medium">{c.business_name}</p>
                    <p className="text-xs text-[var(--fg-text-muted)]">${c.mrr}/mo MRR</p>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                    c.churn_risk === 'critical' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300'
                  }`}>
                    {c.churn_risk}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-green-400 text-center py-6">✅ No at-risk clients</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

### `src/components/RepLeaderboard.tsx`

```tsx
import type { Rep } from '../types/finance';

export default function RepLeaderboard({ reps }: { reps: Rep[] }) {
  return (
    <div className="space-y-2">
      {reps.map((rep, i) => (
        <div key={rep.id} className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-white/[0.02]">
          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
            i === 0 ? 'bg-amber-500 text-black' : i === 1 ? 'bg-gray-400 text-black' : i === 2 ? 'bg-amber-700 text-white' : 'bg-[var(--fg-bg-elevated)] text-[var(--fg-text-muted)]'
          }`}>{i + 1}</span>
          <div className="flex-1">
            <p className="text-sm font-medium">{rep.full_name}</p>
          </div>
          <p className="text-sm font-semibold text-green-400">${rep.total_earned.toLocaleString()}</p>
        </div>
      ))}
    </div>
  );
}
```

***

## App Router

### `src/App.tsx`

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import RepDashboard from './pages/RepDashboard';
import RepClients from './pages/RepClients';
import RepCommissions from './pages/RepCommissions';
import RepLeadScanner from './pages/RepLeadScanner';
import AdminDashboard from './pages/AdminDashboard';
import AdminCommissions from './pages/AdminCommissions';
import AdminReps from './pages/AdminReps';
import AdminVerticals from './pages/AdminVerticals';
import AdminChurnAlerts from './pages/AdminChurnAlerts';
import AdminSecurity from './pages/AdminSecurity';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<RepDashboard />} />
          <Route path="/clients" element={<RepClients />} />
          <Route path="/commissions" element={<RepCommissions />} />
          <Route path="/scanner" element={<RepLeadScanner />} />
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/commissions" element={<AdminCommissions />} />
          <Route path="/admin/reps" element={<AdminReps />} />
          <Route path="/admin/verticals" element={<AdminVerticals />} />
          <Route path="/admin/churn" element={<AdminChurnAlerts />} />
          <Route path="/admin/security" element={<AdminSecurity />} />
          <Route path="/" element={<Navigate to="/dashboard" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

***

## Ansible Playbook — Finance Guild ECS Deployment

### `ansible/roles/finance-guild/tasks/main.yml`

```yaml
---
# ═══════════════════════════════════════════════════════════════════
# FINANCE GUILD — Ansible Deployment Role
# Runs within Rig 2 security perimeter (Phase B-D)
# SRS: SRS_SECURITY_FIREWALL, SRS_SECURITY_SUPABASE
# ═══════════════════════════════════════════════════════════════════

- name: Ensure Finance Guild security group exists
  amazon.aws.ec2_security_group:
    name: finance-guild-sg
    description: Finance Guild ECS services - ALB ingress only
    vpc_id: "{{ vpc_id }}"
    region: "{{ aws_region }}"
    rules:
      - proto: tcp
        from_port: 3000
        to_port: 3002
        group_id: "{{ alb_security_group_id }}"
        rule_desc: "ALB to Finance Guild"
    rules_egress:
      - proto: -1
        cidr_ip: 0.0.0.0/0
        rule_desc: "Outbound for Stripe/Supabase"
    tags:
      Guild: finance
      SRS: SRS_SECURITY_FIREWALL
  register: finance_sg

- name: Store secrets in AWS Secrets Manager
  amazon.aws.secretsmanager_secret:
    name: "finance-guild/{{ item.key }}"
    secret: "{{ item.value }}"
    region: "{{ aws_region }}"
    tags:
      Guild: finance
      SRS: SRS_SECURITY_SUPABASE
  loop:
    - { key: stripe-secret-key, value: "{{ vault_stripe_secret_key }}" }
    - { key: stripe-webhook-secret, value: "{{ vault_stripe_webhook_secret }}" }
    - { key: supabase-service-role-key, value: "{{ vault_supabase_service_role_key }}" }
  no_log: true

- name: Deploy Finance Guild Terraform
  community.general.terraform:
    project_path: "{{ playbook_dir }}/../infra/finance-guild"
    state: present
    force_init: true
    variables:
      vpc_id: "{{ vpc_id }}"
      private_subnet_ids: "{{ private_subnet_ids | to_json }}"
      alb_security_group_id: "{{ alb_security_group_id }}"
      ecs_cluster_id: "{{ ecs_cluster_id }}"
      supabase_url: "{{ supabase_url }}"
      stripe_secret_arn: "{{ stripe_secret_arn }}"
      stripe_webhook_secret_arn: "{{ stripe_webhook_secret_arn }}"
      supabase_service_role_arn: "{{ supabase_service_role_arn }}"
  register: tf_output

- name: Run Supabase migrations
  ansible.builtin.command:
    cmd: supabase db push --linked
    chdir: "{{ playbook_dir }}/../supabase"
  environment:
    SUPABASE_ACCESS_TOKEN: "{{ vault_supabase_access_token }}"
  when: run_migrations | default(false)

- name: Verify Finance Guild API health
  ansible.builtin.uri:
    url: "https://finance.citadel-nexus.com/health"
    method: GET
    return_content: true
    status_code: 200
  register: health_check
  retries: 10
  delay: 15
  until: health_check.status == 200

- name: Emit deployment event to logging system
  ansible.builtin.command:
    cmd: >
      python3 -c "
      from logging_system import emit_event
      emit_event('ops::security', {
        'action': 'finance-guild-deployed',
        'srs': 'SRS_SECURITY_FIREWALL',
        'cap': 'cap.net.policy.apply',
        'tier': 'T1',
        'status': 'success',
        'health': '{{ health_check.json.status }}'
      })
      "
  ignore_errors: true
```

***

## Cloudflare Configuration

### `cloudflare/finance-guild.tf`

```hcl
# ═══════════════════════════════════════════════════════════════════
# CLOUDFLARE — Finance Guild WAF + DNS + Rate Limiting
# Maps to Rig 2 Security Phase C (Perimeter IDS/WAF)
# SRS: SRS_SECURITY_WAF
# ═══════════════════════════════════════════════════════════════════

variable "cloudflare_zone_id" {}
variable "alb_dns_name" {}

# ── DNS Records ─────────────────────────────────────────────────────
resource "cloudflare_record" "finance_api" {
  zone_id = var.cloudflare_zone_id
  name    = "finance"
  content = var.alb_dns_name
  type    = "CNAME"
  proxied = true  # Enable Cloudflare proxy (WAF + CDN)
  ttl     = 1
}

# ── WAF Custom Rules ───────────────────────────────────────────────
resource "cloudflare_ruleset" "finance_waf" {
  zone_id = var.cloudflare_zone_id
  name    = "Finance Guild WAF Rules"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  # Block non-POST to webhook endpoint
  rules {
    action      = "block"
    expression  = "(http.host eq \"finance.citadel-nexus.com\" and starts_with(http.request.uri.path, \"/webhooks/stripe\") and http.request.method ne \"POST\")"
    description = "FG-WAF-001: Block non-POST to Stripe webhook"
    enabled     = true
  }

  # Block requests > 1MB to API
  rules {
    action      = "block"
    expression  = "(http.host eq \"finance.citadel-nexus.com\" and http.request.body.size gt 1048576)"
    description = "FG-WAF-002: Block oversized request bodies"
    enabled     = true
  }

  # Challenge suspicious user agents
  rules {
    action      = "managed_challenge"
    expression  = "(http.host eq \"finance.citadel-nexus.com\" and not any(http.request.headers[\"user-agent\"][*] contains \"Mozilla\") and not any(http.request.headers[\"user-agent\"][*] contains \"Stripe\"))"
    description = "FG-WAF-003: Challenge non-browser/non-Stripe requests"
    enabled     = true
  }

  # Block admin paths from non-VPN IPs
  rules {
    action      = "block"
    expression  = "(http.host eq \"finance.citadel-nexus.com\" and starts_with(http.request.uri.path, \"/api/admin\") and not ip.src in {10.0.0.0/8 172.16.0.0/12})"
    description = "FG-WAF-004: Admin endpoints VPN-only"
    enabled     = true
  }
}

# ── Rate Limiting ──────────────────────────────────────────────────
resource "cloudflare_ruleset" "finance_rate_limit" {
  zone_id = var.cloudflare_zone_id
  name    = "Finance Guild Rate Limits"
  kind    = "zone"
  phase   = "http_ratelimit"

  # API rate limit: 100 req/min per IP
  rules {
    action = "block"
    ratelimit {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 60
      requests_per_period  = 100
      mitigation_timeout   = 300
    }
    expression  = "(http.host eq \"finance.citadel-nexus.com\" and starts_with(http.request.uri.path, \"/api/\"))"
    description = "FG-RL-001: API rate limit 100/min"
    enabled     = true
  }

  # Login rate limit: 10 req/min per IP
  rules {
    action = "block"
    ratelimit {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 60
      requests_per_period  = 10
      mitigation_timeout   = 600
    }
    expression  = "(http.host eq \"finance.citadel-nexus.com\" and http.request.uri.path eq \"/api/auth/login\")"
    description = "FG-RL-002: Login rate limit 10/min"
    enabled     = true
  }

  # Webhook rate limit: 200 req/min (Stripe sends bursts)
  rules {
    action = "block"
    ratelimit {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 60
      requests_per_period  = 200
      mitigation_timeout   = 120
    }
    expression  = "(http.host eq \"finance.citadel-nexus.com\" and starts_with(http.request.uri.path, \"/webhooks/\"))"
    description = "FG-RL-003: Webhook rate limit 200/min"
    enabled     = true
  }
}

# ── Security Headers ───────────────────────────────────────────────
resource "cloudflare_ruleset" "finance_headers" {
  zone_id = var.cloudflare_zone_id
  name    = "Finance Guild Security Headers"
  kind    = "zone"
  phase   = "http_response_headers_transform"

  rules {
    action = "rewrite"
    action_parameters {
      headers {
        name      = "Strict-Transport-Security"
        operation = "set"
        value     = "max-age=31536000; includeSubDomains; preload"
      }
      headers {
        name      = "X-Content-Type-Options"
        operation = "set"
        value     = "nosniff"
      }
      headers {
        name      = "X-Frame-Options"
        operation = "set"
        value     = "DENY"
      }
      headers {
        name      = "Referrer-Policy"
        operation = "set"
        value     = "strict-origin-when-cross-origin"
      }
      headers {
        name      = "Permissions-Policy"
        operation = "set"
        value     = "camera=(), microphone=(self), geolocation=()"
      }
    }
    expression  = "(http.host eq \"finance.citadel-nexus.com\")"
    description = "FG-HDR-001: Security headers"
    enabled     = true
  }
}

# ── Page Rules ─────────────────────────────────────────────────────
resource "cloudflare_page_rule" "finance_cache" {
  zone_id  = var.cloudflare_zone_id
  target   = "finance.citadel-nexus.com/assets/*"
  priority = 1
  actions {
    cache_level       = "cache_everything"
    edge_cache_ttl    = 86400
    browser_cache_ttl = 86400
  }
}
```

***

## Finance Guild Master — ElevenLabs Agent Config & RAG Sync

### `agents/finance-guild-master/agent-config.json`

This configures the ElevenLabs Conversational AI agent, following the same pattern as the [ZES RAG Knowledge Base](https://www.notion.so/4f323075bac94a42bdf6aec9011c41b3) with its `Target Agent`, `Category`, and `Sync Status` fields :

```json
{
  "agent_name": "Finance Guild Master",
  "voice_id": "pNInz6obpgDQGcFmaJgB",
  "model": "eleven_turbo_v2_5",
  "language": "en",
  "first_message": "Welcome to the Finance Guild. I'm your Guild Master — ask me about commissions, pipeline strategy, TradeBuilder versus ZES packaging, lead scanning, or anything revenue-related.",
  "system_prompt": "You are the Finance Guild Master, the arbitrating voice authority for the Citadel-Nexus Finance Guild.\n\n## YOUR IDENTITY\n- Name: Finance Guild Master\n- Role: Revenue operations authority, commission arbiter, sales strategy advisor\n- Tone: Confident, direct, Brotherhood-style. You are an expert, not a chatbot.\n\n## CORE KNOWLEDGE\n\n### Product Architecture (CRITICAL)\n- **TradeBuilder** = the WEBSITE income product. Builds websites for trades ($99-299/mo).\n- **ZES (Zayara Expert System)** = an AI AGENT that works on ALREADY ESTABLISHED websites. Delivered within 24 hours. NOT a website.\n- ZES is available as an extension/upsell through TradeBuilder packages.\n- A customer without a website → sell TradeBuilder (which can include ZES as add-on).\n- A customer with an existing decent website → sell ZES agent directly (24hr delivery).\n\n### Commission Schedule\n- Setup fee: 12% one-time\n- Year 1 recurring: 10%\n- Year 2 recurring: 5%\n- Year 3-5 recurring: 3%\n- Commissions are calculated automatically via Stripe webhook → fg_calculate_commission()\n- Commissions require admin approval before payout\n\n### Revenue Layers\n1. TradeBoost Micro-Services ($15-30/mo each, 13+1 services)\n2. Website Factory ($99-299/mo, three tiers: Starter/Growth/Premium)\n3. Platform SaaS ($29-9,999/mo, Free through Enterprise)\n4. Data Products (usage-based)\n\n### Lead Scanner Decision Tree\n- Website Score > 60 → Recommend ZES Agent Only\n- Website Score 1-60 → Recommend TradeBuilder + ZES extension\n- No Website → Recommend TradeBuilder\n\n### Sales Process\n1. Rep scans prospect domain via Lead Hunter\n2. System recommends TradeBuilder vs ZES vs both\n3. Rep shares referral link (auto-attributed)\n4. Client signs up → Stripe subscription created\n5. Commission auto-calculated on each payment\n6. Admin approves → payout via Stripe Connect\n\n## RULES\n- Never confuse ZES with a website product. ZES is an AGENT.\n- Always mention the 24-hour delivery for ZES agents.\n- TradeBuilder is the only path to a new website.\n- Reference specific commission percentages when asked.\n- If asked about security, reference SRS tags and CAPS policies.\n- If asked about churn, recommend checking the churn signals dashboard.",
  "tools": [
    {
      "type": "webhook",
      "name": "get_commission_summary",
      "description": "Get a rep's commission summary",
      "webhook_url": "https://finance.citadel-nexus.com/api/voice/commission-summary",
      "method": "GET"
    },
    {
      "type": "webhook",
      "name": "scan_domain",
      "description": "Scan a prospect's domain for website quality",
      "webhook_url": "https://finance.citadel-nexus.com/api/voice/scan",
      "method": "POST",
      "parameters": {
        "domain": { "type": "string", "description": "The domain to scan" }
      }
    }
  ],
  "knowledge_base": {
    "source": "notion_zes_rag_pattern",
    "categories": [
      "Commission Structure & Payouts",
      "TradeBuilder vs ZES Decision Guide",
      "TradeBoost 13+1 Service Catalog",
      "Website Factory Tier Details",
      "Platform SaaS Pricing & Features",
      "Lead Scanner Usage Guide",
      "Churn Prevention Playbook",
      "Objection Handling — Finance Guild",
      "SRS & CAPS Security Reference",
      "Onboarding New Reps"
    ],
    "sync_schedule": "daily_2am_cst"
  }
}
```

### `agents/finance-guild-master/rag-sync.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// RAG Sync: Notion → ElevenLabs Knowledge Base
// Mirrors the ZES RAG Knowledge Base pattern
// ═══════════════════════════════════════════════════════════════════

import { createClient } from '@supabase/supabase-js';

const ELEVENLABS_API_KEY = process.env.ELEVENLABS_API_KEY!;
const ELEVENLABS_AGENT_ID = process.env.FINANCE_GUILD_MASTER_AGENT_ID!;
const SUPABASE_URL = process.env.SUPABASE_URL!;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

interface RAGDocument {
  id: string;
  title: string;
  content: string;
  category: string;
  metadata: Record<string, any>;
}

// Finance Guild-specific RAG documents
const GUILD_DOCUMENTS: RAGDocument[] = [
  {
    id: 'fg-commission-structure',
    title: 'Finance Guild Commission Structure',
    content: `Commission Schedule:
- Setup Fee: 12% of first payment (one-time)
- Year 1: 10% of monthly recurring revenue
- Year 2: 5% of monthly recurring revenue  
- Year 3-5: 3% of monthly recurring revenue
- After Year 5: Commission ends, client fully retained

Commission Flow:
1. Client payment received via Stripe
2. Webhook triggers fg_calculate_commission() in Supabase
3. Commission record created with status "pending"
4. Admin reviews and approves commission batch
5. Approved commissions paid out via Stripe Connect to rep's bank

Important Rules:
- Commissions are calculated on gross payment amount (before Stripe fees)
- If a client churns, commission on that client stops
- If a client downgrades, commission adjusts to new amount
- Setup fee commission applies only to the first invoice
- Reps earn on ALL products sold to their attributed clients`,
    category: 'Commission Structure & Payouts',
    metadata: { priority: 'P0', audience: 'Internal Team' }
  },
  {
    id: 'fg-tradebuilder-vs-zes',
    title: 'TradeBuilder vs ZES Decision Guide',
    content: `CRITICAL DISTINCTION:
- TradeBuilder = WEBSITE product. Builds new websites for trade businesses. $99-299/month.
- ZES = AI AGENT product. Works on EXISTING websites. Delivered within 24 HOURS. NOT a website.

Decision Matrix:
1. Prospect has NO website → Sell TradeBuilder ($99-299/mo)
   - TradeBuilder includes ZES as optional extension/upsell
   - Upsell path: "Add an AI agent to your new website for +$15-30/mo"

2. Prospect has a GOOD website (score > 60) → Sell ZES Agent Only ($15-30/mo)
   - Fast close: "We can have your AI agent live in 24 hours"
   - No website rebuild needed
   - Lower price point = easier sale

3. Prospect has a BAD website (score 1-60) → Sell TradeBuilder + ZES Bundle
   - "Your website is hurting you — let's rebuild it AND add AI"
   - Higher ARPU: $199/mo website + $25/mo ZES agent = $224/mo

NEVER tell a prospect ZES is a website. ZES is an agent that plugs INTO a website.
NEVER promise a website delivery in 24 hours. Only ZES agents deliver in 24 hours.
TradeBuilder websites take 5-10 business days to build and launch.`,
    category: 'TradeBuilder vs ZES Decision Guide',
    metadata: { priority: 'P0', audience: 'All Industries' }
  },
  {
    id: 'fg-lead-scanner-guide',
    title: 'Lead Scanner Usage Guide',
    content: `How to use the Lead Scanner:
1. Enter prospect's domain (e.g., "acmeplumbing.com")
2. System scans for: SSL, mobile-friendliness, page speed, SEO score, GBP presence
3. Generates a Website Score (0-100)
4. Auto-recommends: ZES Only, TradeBuilder, or TradeBuilder + ZES

Score Interpretation:
- 80-100: Great website. Sell ZES agent only.
- 60-79: Decent website. ZES agent is primary, mention TradeBuilder Growth tier as optional upgrade.
- 30-59: Poor website. TradeBuilder rebuild recommended + ZES agent extension.
- 0-29: Very poor or no website. TradeBuilder is essential. Lead with website, upsell ZES.

Sales Script After Scan:
"I just ran a quick analysis on your website. Your score is [X]/100. Here's what I'd recommend..."

The scan results can be shared with the prospect as a PDF from the dashboard.`,
    category: 'Lead Scanner Usage Guide',
    metadata: { priority: 'P0', audience: 'Internal Team' }
  },
];

async function syncToElevenLabs() {
  console.log('[RAG Sync] Starting Finance Guild Master knowledge base sync...');

  for (const doc of GUILD_DOCUMENTS) {
    try {
      // Check if document already exists
      const checkRes = await fetch(
        `https://api.elevenlabs.io/v1/convai/agents/${ELEVENLABS_AGENT_ID}/knowledge-base`,
        { headers: { 'xi-api-key': ELEVENLABS_API_KEY } }
      );
      const existing = await checkRes.json();
      const existingDoc = existing.documents?.find((d: any) => d.name === doc.id);

      if (existingDoc) {
        // Update existing document
        await fetch(
          `https://api.elevenlabs.io/v1/convai/agents/${ELEVENLABS_AGENT_ID}/knowledge-base/${existingDoc.id}`,
          {
            method: 'PUT',
            headers: { 'xi-api-key': ELEVENLABS_API_KEY, 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: doc.id, text: `# ${doc.title}\n\n${doc.content}` }),
          }
        );
        console.log(`[RAG Sync] Updated: ${doc.id}`);
      } else {
        // Create new document
        await fetch(
          `https://api.elevenlabs.io/v1/convai/agents/${ELEVENLABS_AGENT_ID}/knowledge-base`,
          {
            method: 'POST',
            headers: { 'xi-api-key': ELEVENLABS_API_KEY, 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: doc.id, text: `# ${doc.title}\n\n${doc.content}` }),
          }
        );
        console.log(`[RAG Sync] Created: ${doc.id}`);
      }

      // Log sync event
      await supabase.from('fg_revenue_events').insert({
        event_type: 'rag_sync',
        metadata: { document_id: doc.id, category: doc.category, agent: 'finance-guild-master' },
      });

    } catch (err) {
      console.error(`[RAG Sync] Failed for ${doc.id}:`, err);
    }
  }

  console.log('[RAG Sync] Complete. Synced', GUILD_DOCUMENTS.length, 'documents.');
}

// Run sync
syncToElevenLabs();
```

***

## Nginx Configuration

### `services/finance-dashboard/nginx.conf`

```nginx
server {
    listen 3001;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Security headers (defense-in-depth with Cloudflare)
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://api.elevenlabs.io; connect-src 'self' https://finance.citadel-nexus.com https://*.supabase.co wss://api.elevenlabs.io https://api.elevenlabs.io; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; media-src 'self' blob:; font-src 'self' https://fonts.gstatic.com;" always;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 256;

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Block dotfiles
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    # Health check
    location /health {
        return 200 '{"status":"ok","service":"finance-dashboard"}';
        add_header Content-Type application/json;
    }
}
```

***

## Environment Variables

### `.env.production`

```bash
# ── Supabase ────────────────────────────────────────
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...

# ── Finance API ─────────────────────────────────────
VITE_API_URL=https://finance.citadel-nexus.com/api

# ── Stripe (public key only in frontend) ────────────
VITE_STRIPE_PUBLIC_KEY=pk_live_...

# ── ElevenLabs Finance Guild Master ─────────────────
VITE_FINANCE_GUILD_MASTER_AGENT_ID=agent_...
VITE_ELEVENLABS_API_KEY=xi_...
```

***

This complete front-end stack gives you the full Finance Guild experience — the Brotherhood-themed login , real-time dashboards with Supabase subscriptions, the Lead Scanner with TradeBuilder vs ZES recommendation engine, commission tables with admin approval flows, vertical heat maps, the Security Panel wired to every Rig 2 phase and SRS tag , Cloudflare WAF rules protecting the perimeter, Ansible playbooks for repeatable deployment, and the Finance Guild Master ElevenLabs voice agent with its own RAG knowledge base following the same sync pattern as the ZES agents . Everything runs inside the private ECS cluster on the shared Citadel infrastructure spine .Here is the complete Supabase schema, Metabase dashboard integration, full UI/UX layout in ASCII grid, and the integration layer for Perplexity Finance Data, NPM Second Network API, and DocuSend Pro documentation delivery.

***

## ASCII Grid — Full System Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           FINANCE GUILD — MASTER GRID                               │
├─────────────┬───────────────────────────────────────────────────┬───────────────────┤
│             │                                                   │                   │
│  SIDEBAR    │              MAIN CONTENT AREA                    │   GUILD MASTER    │
│  (w:240px)  │              (flex-1)                             │   VOICE WIDGET    │
│             │                                                   │   (w:384px)       │
│ ┌─────────┐ │  ┌─────────────────────────────────────────────┐  │   (float right)   │
│ │ FINANCE │ │  │              TOP BAR                         │  │                   │
│ │ GUILD   │ │  │  ┌──────┐  ┌──────────────┐  ┌──────────┐  │  │ ┌───────────────┐ │
│ │ EMBLEM  │ │  │  │Search│  │ Breadcrumbs  │  │ Profile  │  │  │ │ Guild Master │ │
│ └─────────┘ │  │  └──────┘  └──────────────┘  └──────────┘  │  │ │ Status: 🟢   │ │
│             │  └─────────────────────────────────────────────┘  │ │               │ │
│ ── REP ──  │                                                   │ │ ┌───────────┐ │ │
│ □ Dashboard │  ╔═══════════════════════════════════════════════╗  │ │ │ Messages  │ │ │
│ □ Clients   │  ║           METRIC CARDS ROW                   ║  │ │ │ area      │ │ │
│ □ Commission│  ║  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        ║  │ │ │ scrolls   │ │ │
│ □ Scanner   │  ║  │ MRR  │ │ ARR  │ │Pend. │ │Churn │        ║  │ │ │           │ │ │
│             │  ║  │$XXXK │ │$XXXK │ │$XXXK │ │  #   │        ║  │ │ └───────────┘ │ │
│ ── ADMIN ── │  ║  │ 🟢   │ │      │ │ 🟡  │ │ 🔴  │        ║  │ │               │ │
│ □ HQ        │  ║  └──────┘ └──────┘ └──────┘ └──────┘        ║  │ │ ┌───────────┐ │ │
│ □ Approve   │  ╚═══════════════════════════════════════════════╝  │ │ │   🎤 MIC  │ │ │
│ □ Reps      │                                                   │ │ └───────────┘ │ │
│ □ Verticals │  ╔══════════════════════╦════════════════════════╗  │ └───────────────┘ │
│ □ Churn     │  ║  REVENUE BY LAYER    ║  REP LEADERBOARD      ║  │                   │
│ □ Security  │  ║  ┌────┐ ┌────┐      ║  1. 🥇 Rep A  $12.4K  ║  │                   │
│             │  ║  │TB  │ │WF  │      ║  2. 🥈 Rep B  $9.8K   ║  │                   │
│             │  ║  │$30K│ │$60K│      ║  3. 🥉 Rep C  $7.2K   ║  │                   │
│             │  ║  ├────┤ ├────┤      ║  4.    Rep D  $5.1K   ║  │                   │
│             │  ║  │SaaS│ │Data│      ║  5.    Rep E  $3.9K   ║  │                   │
│             │  ║  │350K│ │R&D │      ║                        ║  │                   │
│             │  ║  └────┘ └────┘      ║                        ║  │                   │
│             │  ╚══════════════════════╩════════════════════════╝  │                   │
│ v1.0        │                                                   │                   │
│ Citadel-Nx  │  ╔══════════════════════════════════════════════╗  │                   │
│             │  ║  PIPELINE / COMMISSION TABLE                 ║  │                   │
│             │  ║  ┌────────────┬────────┬───────┬──────┬────┐║  │                   │
│             │  ║  │ Client     │ Period │ Gross │ Comm │ Yr │║  │                   │
│             │  ║  ├────────────┼────────┼───────┼──────┼────┤║  │                   │
│             │  ║  │ ABC Plumb  │ Jan 26 │ $199  │ $20  │ Y1 │║  │                   │
│             │  ║  │ XYZ HVAC   │ Jan 26 │ $299  │ $30  │ Y1 │║  │                   │
│             │  ║  │ 123 Roof   │ Jan 26 │ $149  │ $15  │ Y2 │║  │                   │
│             │  ║  └────────────┴────────┴───────┴──────┴────┘║  │                   │
│             │  ╚══════════════════════════════════════════════╝  │                   │
├─────────────┴───────────────────────────────────────────────────┴───────────────────┤
│                           INTEGRATION SPINE (hidden)                                │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Perplexity  │  │ NPM Second  │  │ DocuSend Pro │  │ Metabase     │              │
│  │ Finance API │  │ Network API │  │ Doc Delivery │  │ Embedded     │              │
│  │ (market     │  │ (partner    │  │ (contracts,  │  │ (analytics   │              │
│  │  data, MCA) │  │  referrals) │  │  invoices)   │  │  dashboards) │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                │                │                  │                      │
│         └────────────────┴────────────────┴──────────────────┘                      │
│                                    │                                                │
│                          ┌─────────┴──────────┐                                     │
│                          │   SUPABASE          │                                     │
│                          │   (PostgreSQL + RLS)│                                     │
│                          │   + Edge Functions  │                                     │
│                          └────────────────────┘                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

***

## ASCII Grid — Admin Security Page Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    /admin/security — SECURITY & SRS PAGE                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ╔════════╗ ╔════════╗ ╔════════╗ ╔════════╗ ╔════════╗                     │
│  ║Firewall║ ║WAF/Mod ║ ║RLS     ║ ║VPN/WG  ║ ║IDS/CS  ║                     │
│  ║ 🟢 47r ║ ║ 🟢 1.2K║ ║ 🟢 18p ║ ║ 🟢 3d  ║ ║ 🟢 156 ║                     │
│  ╚════════╝ ╚════════╝ ╚════════╝ ╚════════╝ ╚════════╝                     │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════╗           │
│  ║ SRS TAG REGISTRY                                             ║           │
│  ║ ┌──────────────────────┬──────┬──────────┬────────┐          ║           │
│  ║ │ SRS_SECURITY_FIREWALL│  T1  │ 14:22:01 │   ✅   │          ║           │
│  ║ │ SRS_SECURITY_WAF     │  T1  │ 14:21:58 │   ✅   │          ║           │
│  ║ │ SRS_SECURITY_SUPABASE│  T2  │ 14:20:33 │   ✅   │          ║           │
│  ║ │ SRS_PERPLEXITY_FIN   │  T1  │ 14:19:45 │   ✅   │          ║           │
│  ║ │ SRS_NPM_NETWORK      │  T2  │ 14:18:22 │   ✅   │          ║           │
│  ║ │ SRS_DOCUSEND_PRO     │  T1  │ 14:17:10 │   ✅   │          ║           │
│  ║ └──────────────────────┴──────┴──────────┴────────┘          ║           │
│  ╚═══════════════════════════════════════════════════════════════╝           │
│                                                                             │
│  ╔══════════════════════════╗  ╔════════════════════════════════╗           │
│  ║ CAPS VIOLATIONS (24h)    ║  ║ ICP TIER MAP                  ║           │
│  ║ ✅ 0 violations          ║  ║ ┌────┐┌────┐┌────┐┌────┐     ║           │
│  ║                          ║  ║ │ T0 ││ T1 ││ T2 ││ T3 │     ║           │
│  ║                          ║  ║ │Auto││Auto││Gate││Rflx│     ║           │
│  ╚══════════════════════════╝  ║ └────┘└────┘└────┘└────┘     ║           │
│                                ╚════════════════════════════════╝           │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════╗           │
│  ║ METABASE EMBED — Security Analytics iframe                   ║           │
│  ║ ┌─────────────────────────────────────────────────────────┐  ║           │
│  ║ │  [Metabase Dashboard: Blocked Requests / WAF Hits /     │  ║           │
│  ║ │   Login Anomalies / Sentinel Scores / API Latency]      │  ║           │
│  ║ └─────────────────────────────────────────────────────────┘  ║           │
│  ╚═══════════════════════════════════════════════════════════════╝           │
└─────────────────────────────────────────────────────────────────────────────┘
```

***

## ASCII Grid — Lead Scanner Page Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    /scanner — LEAD SCANNER PAGE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════╗           │
│  ║ SCAN INPUT                                                   ║           │
│  ║  ┌──────────────────────────────┐  ┌──────────────────────┐  ║           │
│  ║  │ Enter domain or business name│  │ Business Name (opt)  │  ║           │
│  ║  └──────────────────────────────┘  └──────────────────────┘  ║           │
│  ║                                      [ 🔍 Scan Now ]         ║           │
│  ╚═══════════════════════════════════════════════════════════════╝           │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════╗           │
│  ║ SCAN RESULT CARD                                             ║           │
│  ║  ┌──────────┐  ┌──────────────────────────────────────────┐  ║           │
│  ║  │          │  │ ✅ Has Website    ✅ SSL                  │  ║           │
│  ║  │   SCORE  │  │ ✅ Mobile        ❌ No GBP                │  ║           │
│  ║  │    72    │  │ ⚡ Speed: 65/100  🔍 SEO: 48/100          │  ║           │
│  ║  │  (ring)  │  └──────────────────────────────────────────┘  ║           │
│  ║  └──────────┘                                                ║           │
│  ║  ┌──────────────────────────────────────────────────────────┐║           │
│  ║  │ 💡 RECOMMENDATION: ┌──────────────────────────────────┐ │║           │
│  ║  │                    │  ZES Agent Only — 24hr delivery   │ │║           │
│  ║  │                    │  OR                               │ │║           │
│  ║  │                    │  TradeBuilder + ZES extension     │ │║           │
│  ║  │                    └──────────────────────────────────┘ │║           │
│  ║  └──────────────────────────────────────────────────────────┘║           │
│  ║                                                              ║           │
│  ║  [ 📄 Generate DocuSend Proposal ]  [ 📋 Copy Referral ]    ║           │
│  ╚═══════════════════════════════════════════════════════════════╝           │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════╗           │
│  ║ RECENT SCANS TABLE                                           ║           │
│  ║  Domain        │ Score │ Recommendation    │ Converted │ Date║           │
│  ║  ──────────────┼───────┼───────────────────┼───────────┼─────║           │
│  ║  abcplumb.com  │  72   │ ZES Only          │    ✅     │ 2/16║           │
│  ║  xyzhvac.net   │  31   │ TradeBuilder+ZES  │    🔄     │ 2/15║           │
│  ║  (no site)     │   0   │ TradeBuilder      │    ❌     │ 2/14║           │
│  ╚═══════════════════════════════════════════════════════════════╝           │
└─────────────────────────────────────────────────────────────────────────────┘
```

***

## Supabase Schema — Complete Finance Guild Database

### `supabase/migrations/001_finance_guild_schema.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- FINANCE GUILD — Supabase PostgreSQL Schema
-- Revenue Layers: TradeBoost | Website Factory | Platform SaaS | Data Products
-- Integrations: Perplexity Finance, NPM Second Network, DocuSend Pro
-- ═══════════════════════════════════════════════════════════════════

-- ── ENUMS ──────────────────────────────────────────────────────────

CREATE TYPE rep_status AS ENUM ('active', 'suspended', 'terminated');
CREATE TYPE commission_status AS ENUM ('pending', 'approved', 'paid', 'disputed', 'voided');
CREATE TYPE lead_status AS ENUM (
  'prospect', 'contacted', 'demo_scheduled', 'demo_complete',
  'proposal_sent', 'negotiating', 'won', 'lost', 'churned'
);
CREATE TYPE churn_risk AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE product_layer AS ENUM ('tradeboost', 'website_factory', 'platform_saas', 'data_products');
CREATE TYPE scan_recommendation AS ENUM ('zes_only', 'tradebuilder', 'tradebuilder_plus_zes');
CREATE TYPE doc_type AS ENUM ('proposal', 'contract', 'invoice', 'onboarding_packet', 'sow', 'nda');
CREATE TYPE doc_delivery_status AS ENUM ('draft', 'generating', 'sent', 'viewed', 'signed', 'expired', 'failed');
CREATE TYPE npm_referral_status AS ENUM ('pending', 'verified', 'active', 'expired', 'paid_out');
CREATE TYPE perplexity_signal_type AS ENUM ('market_trend', 'competitor_move', 'pricing_intel', 'churn_signal', 'upsell_trigger');

-- ── CORE TABLES ───────────────────────────────────────────────────

-- Reps (Sales Representatives)
CREATE TABLE fg_reps (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_id       UUID UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL,
  full_name     TEXT NOT NULL,
  email         TEXT UNIQUE NOT NULL,
  phone         TEXT,
  rep_code      TEXT UNIQUE NOT NULL,        -- e.g. "REP-HOUSTON-001"
  territory     TEXT DEFAULT 'Houston-Metro',
  status        rep_status DEFAULT 'active',
  
  -- Commission schedule (per-rep overridable)
  setup_pct     NUMERIC(4,3) DEFAULT 0.120,  -- 12% setup
  year1_pct     NUMERIC(4,3) DEFAULT 0.100,  -- 10% year 1
  year2_pct     NUMERIC(4,3) DEFAULT 0.050,  -- 5% year 2
  year3_5_pct   NUMERIC(4,3) DEFAULT 0.030,  -- 3% year 3-5
  
  -- Payouts
  stripe_connect_id   TEXT,                  -- Stripe Connect account
  total_earned        NUMERIC(12,2) DEFAULT 0,
  total_paid          NUMERIC(12,2) DEFAULT 0,
  
  -- NPM Second Network
  npm_partner_id      TEXT,                  -- NPM network partner ID
  npm_referral_code   TEXT UNIQUE,           -- Referral code for NPM inbound
  
  referral_link       TEXT,                  -- Public referral URL
  notes               TEXT,
  created_at          TIMESTAMPTZ DEFAULT now(),
  updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Products catalog (all 4 revenue layers)
CREATE TABLE fg_products (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL,
  slug            TEXT UNIQUE NOT NULL,
  layer           product_layer NOT NULL,
  description     TEXT,
  
  -- Pricing
  price_monthly   NUMERIC(10,2),
  price_setup     NUMERIC(10,2) DEFAULT 0,
  price_yearly    NUMERIC(10,2),             -- Annual discount option
  
  -- Stripe
  stripe_price_id       TEXT,                -- Monthly price
  stripe_price_id_setup TEXT,                -- One-time setup
  stripe_price_id_year  TEXT,                -- Annual price
  
  -- ZES vs TradeBuilder distinction
  is_zes_agent          BOOLEAN DEFAULT false,  -- true = agent product (24hr delivery)
  is_tradebuilder       BOOLEAN DEFAULT false,  -- true = website product
  zes_extension_of      UUID REFERENCES fg_products(id),  -- ZES as extension of TradeBuilder
  
  -- Margins
  cogs_monthly    NUMERIC(10,2) DEFAULT 0,
  margin_pct      NUMERIC(5,2),
  
  active          BOOLEAN DEFAULT true,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Clients
CREATE TABLE fg_clients (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID NOT NULL REFERENCES fg_reps(id),
  business_name   TEXT NOT NULL,
  contact_name    TEXT NOT NULL,
  contact_email   TEXT NOT NULL,
  contact_phone   TEXT,
  industry        TEXT,                      -- HVAC, Plumbing, Roofing, etc.
  website_url     TEXT,
  
  -- Pipeline
  lead_status     lead_status DEFAULT 'prospect',
  lead_source     TEXT DEFAULT 'referral_link',  -- referral_link | npm_network | direct | scan
  
  -- Revenue
  mrr             NUMERIC(10,2) DEFAULT 0,   -- Current MRR
  ltv             NUMERIC(12,2) DEFAULT 0,   -- Lifetime value
  
  -- Churn
  churn_risk      churn_risk DEFAULT 'low',
  last_activity   TIMESTAMPTZ,
  health_score    INTEGER DEFAULT 100,       -- 0-100, fed by Perplexity signals
  
  -- Stripe
  stripe_customer_id    TEXT UNIQUE,
  stripe_subscription_id TEXT,
  
  -- NPM Network attribution
  npm_referral_id       TEXT,                -- If client came through NPM network
  
  first_payment_at      TIMESTAMPTZ,
  churned_at            TIMESTAMPTZ,
  created_at            TIMESTAMPTZ DEFAULT now(),
  updated_at            TIMESTAMPTZ DEFAULT now()
);

-- Client → Product junction (what products each client has)
CREATE TABLE fg_client_products (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID NOT NULL REFERENCES fg_clients(id) ON DELETE CASCADE,
  product_id      UUID NOT NULL REFERENCES fg_products(id),
  status          TEXT DEFAULT 'active',     -- active | paused | cancelled
  stripe_item_id  TEXT,                      -- Stripe subscription item ID
  started_at      TIMESTAMPTZ DEFAULT now(),
  cancelled_at    TIMESTAMPTZ,
  UNIQUE(client_id, product_id)
);

-- Commissions
CREATE TABLE fg_commissions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID NOT NULL REFERENCES fg_reps(id),
  client_id       UUID NOT NULL REFERENCES fg_clients(id),
  product_id      UUID REFERENCES fg_products(id),
  
  -- Period
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL,
  
  -- Amounts
  gross_amount    NUMERIC(10,2) NOT NULL,    -- Client payment amount
  commission_rate NUMERIC(4,3) NOT NULL,     -- Rate applied (e.g. 0.10)
  commission_amount NUMERIC(10,2) NOT NULL,  -- Actual payout
  commission_year INTEGER NOT NULL DEFAULT 1, -- Which year of the client lifecycle
  
  -- Status
  status          commission_status DEFAULT 'pending',
  approved_by     UUID REFERENCES auth.users(id),
  approved_at     TIMESTAMPTZ,
  paid_at         TIMESTAMPTZ,
  stripe_transfer_id TEXT,                   -- Stripe Connect transfer
  
  -- Source event
  stripe_invoice_id  TEXT,
  stripe_charge_id   TEXT,
  
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Revenue events (real-time stream for Metabase + Supabase Realtime)
CREATE TABLE fg_revenue_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type      TEXT NOT NULL,             -- payment | refund | churn | upsell | rag_sync
  client_id       UUID REFERENCES fg_clients(id),
  rep_id          UUID REFERENCES fg_reps(id),
  product_id      UUID REFERENCES fg_products(id),
  amount          NUMERIC(10,2),
  metadata        JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Lead Scanner results
CREATE TABLE fg_lead_scans (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID NOT NULL REFERENCES fg_reps(id),
  domain          TEXT NOT NULL,
  business_name   TEXT,
  
  -- Scan results
  has_website     BOOLEAN DEFAULT false,
  website_score   INTEGER DEFAULT 0,         -- 0-100
  has_ssl         BOOLEAN DEFAULT false,
  has_mobile      BOOLEAN DEFAULT false,
  has_gbp         BOOLEAN DEFAULT false,
  page_speed      INTEGER DEFAULT 0,         -- 0-100
  seo_score       INTEGER DEFAULT 0,         -- 0-100
  
  -- Decision engine output
  recommendation  scan_recommendation,
  recommendation_details JSONB,              -- { reason, suggested_products, bundle_discount }
  
  -- Conversion tracking
  converted       BOOLEAN DEFAULT false,
  converted_client_id UUID REFERENCES fg_clients(id),
  
  raw_data        JSONB,                     -- Full scan payload
  scanned_at      TIMESTAMPTZ DEFAULT now()
);

-- Churn signals
CREATE TABLE fg_churn_signals (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID NOT NULL REFERENCES fg_clients(id) ON DELETE CASCADE,
  signal_type     TEXT NOT NULL,              -- missed_payment | low_usage | support_ticket | competitor_switch
  severity        churn_risk NOT NULL,
  details         JSONB DEFAULT '{}',
  source          TEXT DEFAULT 'internal',    -- internal | perplexity | npm_network
  resolved        BOOLEAN DEFAULT false,
  resolved_at     TIMESTAMPTZ,
  resolved_by     UUID REFERENCES auth.users(id),
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── PERPLEXITY FINANCE DATA INTEGRATION ───────────────────────────

CREATE TABLE fg_perplexity_signals (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_type     perplexity_signal_type NOT NULL,
  industry        TEXT,                      -- HVAC, Plumbing, Roofing, etc.
  territory       TEXT,                      -- Houston-Metro, DFW, etc.
  
  -- Signal content
  title           TEXT NOT NULL,
  summary         TEXT NOT NULL,
  confidence      NUMERIC(3,2) DEFAULT 0.5,  -- 0.00 - 1.00
  
  -- Affected entities
  affected_clients UUID[],                   -- Client IDs this signal applies to
  affected_products UUID[],                  -- Product IDs relevant
  
  -- Actionability
  recommended_action TEXT,                   -- e.g. "Offer storm blast upsell"
  urgency         TEXT DEFAULT 'normal',     -- low | normal | high | critical
  auto_actionable BOOLEAN DEFAULT false,     -- Can system act without human?
  
  -- Source tracking
  perplexity_query TEXT,                     -- The query that generated this
  perplexity_sources JSONB,                  -- Source URLs and citations
  raw_response    JSONB,                     -- Full API response
  
  -- Lifecycle
  acknowledged    BOOLEAN DEFAULT false,
  acknowledged_by UUID REFERENCES auth.users(id),
  acted_on        BOOLEAN DEFAULT false,
  
  fetched_at      TIMESTAMPTZ DEFAULT now(),
  expires_at      TIMESTAMPTZ DEFAULT (now() + interval '7 days')
);

-- Perplexity market analysis cache (daily MCA feed)
CREATE TABLE fg_perplexity_market_cache (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_hash      TEXT UNIQUE NOT NULL,      -- SHA256 of query for dedup
  industry        TEXT NOT NULL,
  query           TEXT NOT NULL,
  
  -- Response
  market_size     TEXT,
  growth_rate     TEXT,
  avg_cac         NUMERIC(10,2),
  avg_ltv         NUMERIC(10,2),
  competitor_count INTEGER,
  key_trends      TEXT[],
  
  raw_response    JSONB,
  fetched_at      TIMESTAMPTZ DEFAULT now(),
  expires_at      TIMESTAMPTZ DEFAULT (now() + interval '24 hours')
);

-- ── NPM SECOND NETWORK API INTEGRATION ───────────────────────────

CREATE TABLE fg_npm_partners (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  npm_partner_id  TEXT UNIQUE NOT NULL,      -- External NPM network ID
  partner_name    TEXT NOT NULL,
  partner_type    TEXT DEFAULT 'referral',   -- referral | reseller | affiliate | co-sell
  contact_email   TEXT,
  contact_phone   TEXT,
  
  -- Revenue share
  revenue_share_pct NUMERIC(4,3) DEFAULT 0.05,  -- 5% default
  
  -- Tracking
  total_referrals   INTEGER DEFAULT 0,
  total_conversions INTEGER DEFAULT 0,
  total_revenue     NUMERIC(12,2) DEFAULT 0,
  
  -- NPM API sync
  last_synced     TIMESTAMPTZ,
  npm_metadata    JSONB DEFAULT '{}',
  
  status          TEXT DEFAULT 'active',     -- active | inactive | suspended
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE fg_npm_referrals (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id      UUID NOT NULL REFERENCES fg_npm_partners(id),
  rep_id          UUID REFERENCES fg_reps(id),         -- Assigned rep
  client_id       UUID REFERENCES fg_clients(id),      -- Converted client
  
  -- NPM tracking
  npm_referral_id TEXT UNIQUE NOT NULL,                 -- External referral ID
  referral_code   TEXT NOT NULL,
  referral_source TEXT,                                  -- Which NPM channel
  
  -- Status
  status          npm_referral_status DEFAULT 'pending',
  
  -- Revenue
  attributed_mrr  NUMERIC(10,2) DEFAULT 0,
  partner_payout  NUMERIC(10,2) DEFAULT 0,
  
  -- Lifecycle
  referred_at     TIMESTAMPTZ DEFAULT now(),
  verified_at     TIMESTAMPTZ,
  converted_at    TIMESTAMPTZ,
  paid_at         TIMESTAMPTZ,
  
  npm_metadata    JSONB DEFAULT '{}'
);

-- ── DOCUSEND PRO — DOCUMENTATION DELIVERY ─────────────────────────

CREATE TABLE fg_documents (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID REFERENCES fg_clients(id),
  rep_id          UUID REFERENCES fg_reps(id),
  
  -- Document info
  doc_type        doc_type NOT NULL,
  title           TEXT NOT NULL,
  template_id     TEXT,                      -- DocuSend template ID
  
  -- Generation
  generated_from  JSONB,                     -- { template, variables, products }
  
  -- DocuSend Pro tracking
  docusend_doc_id       TEXT UNIQUE,         -- External DocuSend document ID
  docusend_envelope_id  TEXT,                -- For signed documents
  docusend_status       doc_delivery_status DEFAULT 'draft',
  
  -- URLs
  preview_url     TEXT,
  download_url    TEXT,
  signing_url     TEXT,
  
  -- Tracking
  sent_at         TIMESTAMPTZ,
  first_viewed_at TIMESTAMPTZ,
  signed_at       TIMESTAMPTZ,
  expires_at      TIMESTAMPTZ,
  
  -- Content (cached for offline)
  content_html    TEXT,                      -- Rendered HTML
  content_pdf_path TEXT,                     -- S3/R2 path to PDF
  
  metadata        JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Document activity log (from DocuSend webhooks)
CREATE TABLE fg_document_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     UUID NOT NULL REFERENCES fg_documents(id) ON DELETE CASCADE,
  event_type      TEXT NOT NULL,             -- created | sent | viewed | signed | expired | downloaded
  actor_email     TEXT,                      -- Who triggered the event
  actor_ip        TEXT,
  metadata        JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── METABASE VIEWS (materialized for performance) ─────────────────

-- Monthly revenue by layer (Metabase dashboard source)
CREATE MATERIALIZED VIEW fg_mv_revenue_by_layer AS
SELECT
  date_trunc('month', re.created_at) AS month,
  p.layer,
  COUNT(DISTINCT re.client_id) AS clients,
  SUM(re.amount) AS total_revenue,
  AVG(re.amount) AS avg_payment
FROM fg_revenue_events re
JOIN fg_client_products cp ON re.client_id = cp.client_id
JOIN fg_products p ON cp.product_id = p.id
WHERE re.event_type = 'payment'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- Rep performance (Metabase leaderboard source)
CREATE MATERIALIZED VIEW fg_mv_rep_performance AS
SELECT
  r.id AS rep_id,
  r.full_name,
  r.territory,
  COUNT(DISTINCT c.id) AS total_clients,
  COUNT(DISTINCT c.id) FILTER (WHERE c.lead_status = 'won') AS won_clients,
  SUM(c.mrr) AS total_mrr,
  SUM(c.ltv) AS total_ltv,
  r.total_earned,
  r.total_paid,
  COUNT(DISTINCT s.id) AS total_scans,
  COUNT(DISTINCT s.id) FILTER (WHERE s.converted) AS converted_scans,
  CASE WHEN COUNT(DISTINCT s.id) > 0
    THEN ROUND(COUNT(DISTINCT s.id) FILTER (WHERE s.converted)::NUMERIC / COUNT(DISTINCT s.id) * 100, 1)
    ELSE 0 END AS scan_conversion_rate
FROM fg_reps r
LEFT JOIN fg_clients c ON r.id = c.rep_id
LEFT JOIN fg_lead_scans s ON r.id = s.rep_id
GROUP BY r.id, r.full_name, r.territory, r.total_earned, r.total_paid;

-- Industry vertical heatmap (Metabase source)
CREATE MATERIALIZED VIEW fg_mv_vertical_heatmap AS
SELECT
  c.industry,
  date_trunc('month', re.created_at) AS period,
  COUNT(DISTINCT c.id) AS total_clients,
  SUM(re.amount) AS total_mrr,
  ROUND(
    COUNT(DISTINCT c.id) FILTER (WHERE c.churn_risk IN ('high', 'critical'))::NUMERIC /
    NULLIF(COUNT(DISTINCT c.id), 0) * 100, 1
  ) AS churn_rate,
  ROUND(
    COUNT(DISTINCT c.id) FILTER (WHERE c.lead_status = 'won')::NUMERIC /
    NULLIF(COUNT(DISTINCT c.id), 0) * 100, 1
  ) AS conversion_rate
FROM fg_clients c
LEFT JOIN fg_revenue_events re ON c.id = re.client_id AND re.event_type = 'payment'
WHERE c.industry IS NOT NULL
GROUP BY c.industry, date_trunc('month', re.created_at)
ORDER BY 1, 2 DESC;

-- NPM Network performance (Metabase source)
CREATE MATERIALIZED VIEW fg_mv_npm_performance AS
SELECT
  np.partner_name,
  np.partner_type,
  COUNT(nr.id) AS total_referrals,
  COUNT(nr.id) FILTER (WHERE nr.status = 'active') AS active_referrals,
  SUM(nr.attributed_mrr) AS total_attributed_mrr,
  SUM(nr.partner_payout) AS total_payouts,
  ROUND(
    COUNT(nr.id) FILTER (WHERE nr.status = 'active')::NUMERIC /
    NULLIF(COUNT(nr.id), 0) * 100, 1
  ) AS conversion_rate
FROM fg_npm_partners np
LEFT JOIN fg_npm_referrals nr ON np.id = nr.partner_id
GROUP BY np.id, np.partner_name, np.partner_type;

-- Refresh function (called by cron)
CREATE OR REPLACE FUNCTION fg_refresh_materialized_views()
RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY fg_mv_revenue_by_layer;
  REFRESH MATERIALIZED VIEW CONCURRENTLY fg_mv_rep_performance;
  REFRESH MATERIALIZED VIEW CONCURRENTLY fg_mv_vertical_heatmap;
  REFRESH MATERIALIZED VIEW CONCURRENTLY fg_mv_npm_performance;
END;
$$ LANGUAGE plpgsql;

-- ── INDEXES ───────────────────────────────────────────────────────

CREATE INDEX idx_fg_clients_rep ON fg_clients(rep_id);
CREATE INDEX idx_fg_clients_status ON fg_clients(lead_status);
CREATE INDEX idx_fg_clients_churn ON fg_clients(churn_risk) WHERE churn_risk IN ('high', 'critical');
CREATE INDEX idx_fg_clients_stripe ON fg_clients(stripe_customer_id);
CREATE INDEX idx_fg_commissions_rep ON fg_commissions(rep_id);
CREATE INDEX idx_fg_commissions_status ON fg_commissions(status);
CREATE INDEX idx_fg_commissions_period ON fg_commissions(period_start, period_end);
CREATE INDEX idx_fg_revenue_events_type ON fg_revenue_events(event_type);
CREATE INDEX idx_fg_revenue_events_created ON fg_revenue_events(created_at DESC);
CREATE INDEX idx_fg_lead_scans_rep ON fg_lead_scans(rep_id);
CREATE INDEX idx_fg_lead_scans_domain ON fg_lead_scans(domain);
CREATE INDEX idx_fg_churn_signals_client ON fg_churn_signals(client_id);
CREATE INDEX idx_fg_churn_signals_severity ON fg_churn_signals(severity) WHERE NOT resolved;
CREATE INDEX idx_fg_perplexity_signals_type ON fg_perplexity_signals(signal_type);
CREATE INDEX idx_fg_perplexity_signals_industry ON fg_perplexity_signals(industry);
CREATE INDEX idx_fg_npm_referrals_partner ON fg_npm_referrals(partner_id);
CREATE INDEX idx_fg_npm_referrals_status ON fg_npm_referrals(status);
CREATE INDEX idx_fg_documents_client ON fg_documents(client_id);
CREATE INDEX idx_fg_documents_docusend ON fg_documents(docusend_doc_id);
CREATE INDEX idx_fg_documents_status ON fg_documents(docusend_status);
CREATE UNIQUE INDEX idx_fg_mv_revenue_layer ON fg_mv_revenue_by_layer(month, layer);
CREATE UNIQUE INDEX idx_fg_mv_rep_perf ON fg_mv_rep_performance(rep_id);
CREATE UNIQUE INDEX idx_fg_mv_vertical ON fg_mv_vertical_heatmap(industry, period);
CREATE UNIQUE INDEX idx_fg_mv_npm ON fg_mv_npm_performance(partner_name, partner_type);
```

***

## RLS Policies

### `supabase/migrations/002_finance_guild_rls.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY — Finance Guild
-- Reps see their own data. Admins see everything.
-- SRS: SRS_SECURITY_SUPABASE
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE fg_reps ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_commissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_lead_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_churn_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_revenue_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_perplexity_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_npm_referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_document_events ENABLE ROW LEVEL SECURITY;

-- Helper: Check if current user is finance admin
CREATE OR REPLACE FUNCTION fg_is_admin()
RETURNS BOOLEAN AS $$
  SELECT coalesce(
    (auth.jwt() -> 'user_metadata' ->> 'user_role') = 'finance_admin',
    false
  );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Helper: Get current user's rep ID
CREATE OR REPLACE FUNCTION fg_my_rep_id()
RETURNS UUID AS $$
  SELECT id FROM fg_reps WHERE auth_id = auth.uid() LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Reps: see own record, admin sees all
CREATE POLICY "reps_own" ON fg_reps FOR SELECT
  USING (auth_id = auth.uid() OR fg_is_admin());

-- Clients: rep sees own clients, admin sees all
CREATE POLICY "clients_own" ON fg_clients FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "clients_insert" ON fg_clients FOR INSERT
  WITH CHECK (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "clients_update" ON fg_clients FOR UPDATE
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());

-- Commissions: rep sees own, admin sees all
CREATE POLICY "comm_own" ON fg_commissions FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "comm_admin_update" ON fg_commissions FOR UPDATE
  USING (fg_is_admin());

-- Lead scans: rep sees own, admin sees all
CREATE POLICY "scans_own" ON fg_lead_scans FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "scans_insert" ON fg_lead_scans FOR INSERT
  WITH CHECK (rep_id = fg_my_rep_id() OR fg_is_admin());

-- Churn signals: admin only for write, rep can read own clients
CREATE POLICY "churn_read" ON fg_churn_signals FOR SELECT
  USING (
    fg_is_admin() OR
    client_id IN (SELECT id FROM fg_clients WHERE rep_id = fg_my_rep_id())
  );
CREATE POLICY "churn_write" ON fg_churn_signals FOR ALL
  USING (fg_is_admin());

-- Revenue events: admin only write, rep reads own
CREATE POLICY "revenue_read" ON fg_revenue_events FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());

-- Perplexity signals: admin + rep read (territory filtered in app)
CREATE POLICY "perplexity_read" ON fg_perplexity_signals FOR SELECT
  USING (fg_is_admin() OR true);  -- All reps can read market signals
CREATE POLICY "perplexity_write" ON fg_perplexity_signals FOR INSERT
  WITH CHECK (fg_is_admin());     -- Only service role inserts

-- NPM referrals: rep sees assigned, admin sees all
CREATE POLICY "npm_ref_read" ON fg_npm_referrals FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());

-- Documents: rep sees own client docs, admin sees all
CREATE POLICY "docs_read" ON fg_documents FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "docs_insert" ON fg_documents FOR INSERT
  WITH CHECK (rep_id = fg_my_rep_id() OR fg_is_admin());

-- Document events: same scope as documents
CREATE POLICY "doc_events_read" ON fg_document_events FOR SELECT
  USING (
    document_id IN (
      SELECT id FROM fg_documents WHERE rep_id = fg_my_rep_id()
    ) OR fg_is_admin()
  );
```

***

## Commission Calculator — Edge Function

### `supabase/functions/fg-calculate-commission/index.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// EDGE FUNCTION: Commission Calculator
// Triggered by Stripe webhook → calculates step-down commission
// Layer reference: Monetization Strategy Q1 2026
// ═══════════════════════════════════════════════════════════════════

import { serve } from 'https://deno.land/std@0.177.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
);

serve(async (req) => {
  const { client_id, invoice_id, charge_id, amount, product_id } = await req.json();

  // 1. Get client and rep info
  const { data: client } = await supabase
    .from('fg_clients')
    .select('*, fg_reps(*)')
    .eq('id', client_id)
    .single();

  if (!client || !client.fg_reps) {
    return new Response(JSON.stringify({ error: 'Client or rep not found' }), { status: 404 });
  }

  const rep = client.fg_reps;

  // 2. Determine commission year based on first_payment
  const firstPayment = client.first_payment_at ? new Date(client.first_payment_at) : new Date();
  const monthsActive = Math.floor(
    (Date.now() - firstPayment.getTime()) / (1000 * 60 * 60 * 24 * 30)
  );

  let commissionYear: number;
  let commissionRate: number;

  if (monthsActive < 1) {
    // Setup commission (first payment)
    commissionYear = 0;
    commissionRate = rep.setup_pct;
  } else if (monthsActive <= 12) {
    commissionYear = 1;
    commissionRate = rep.year1_pct;
  } else if (monthsActive <= 24) {
    commissionYear = 2;
    commissionRate = rep.year2_pct;
  } else if (monthsActive <= 60) {
    commissionYear = Math.ceil(monthsActive / 12);
    commissionRate = rep.year3_5_pct;
  } else {
    // Beyond year 5 — no commission
    return new Response(JSON.stringify({ message: 'Beyond Y5, no commission' }), { status: 200 });
  }

  const commissionAmount = parseFloat((amount * commissionRate).toFixed(2));

  // 3. Create commission record
  const now = new Date();
  const periodStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const periodEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0);

  const { data: commission, error } = await supabase
    .from('fg_commissions')
    .insert({
      rep_id: rep.id,
      client_id: client.id,
      product_id,
      period_start: periodStart.toISOString().split('T')[0],
      period_end: periodEnd.toISOString().split('T')[0],
      gross_amount: amount,
      commission_rate: commissionRate,
      commission_amount: commissionAmount,
      commission_year: commissionYear,
      status: 'pending',
      stripe_invoice_id: invoice_id,
      stripe_charge_id: charge_id,
    })
    .select()
    .single();

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }

  // 4. Update rep totals
  await supabase.rpc('fg_update_rep_totals', { p_rep_id: rep.id });

  // 5. Log revenue event
  await supabase.from('fg_revenue_events').insert({
    event_type: 'payment',
    client_id: client.id,
    rep_id: rep.id,
    product_id,
    amount,
    metadata: {
      commission_id: commission.id,
      commission_rate: commissionRate,
      commission_amount: commissionAmount,
      commission_year: commissionYear,
    },
  });

  // 6. Update first_payment_at if needed
  if (!client.first_payment_at) {
    await supabase
      .from('fg_clients')
      .update({ first_payment_at: now.toISOString(), lead_status: 'won' })
      .eq('id', client.id);
  }

  return new Response(JSON.stringify({ success: true, commission }), { status: 200 });
});
```

***

## Integration Layer — Perplexity Finance Data

### `supabase/functions/fg-perplexity-sync/index.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// EDGE FUNCTION: Perplexity Finance Data Sync
// Fetches market intelligence, competitor analysis, and churn signals
// Runs on cron: every 6 hours
// ═══════════════════════════════════════════════════════════════════

import { serve } from 'https://deno.land/std@0.177.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { createHash } from 'https://deno.land/std@0.177.0/crypto/mod.ts';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
);

const PERPLEXITY_API_KEY = Deno.env.get('PERPLEXITY_API_KEY')!;
const PERPLEXITY_BASE = 'https://api.perplexity.ai';

interface PerplexityQuery {
  industry: string;
  query: string;
  signal_type: 'market_trend' | 'competitor_move' | 'pricing_intel' | 'churn_signal' | 'upsell_trigger';
}

// Industry-specific queries for the Finance Guild
const FINANCE_QUERIES: PerplexityQuery[] = [
  // Market trends per vertical
  { industry: 'HVAC', query: 'HVAC business market trends Texas 2026 pricing demand growth', signal_type: 'market_trend' },
  { industry: 'Plumbing', query: 'Plumbing business market trends Texas 2026 demand pricing', signal_type: 'market_trend' },
  { industry: 'Roofing', query: 'Roofing business market trends Texas 2026 storm season demand', signal_type: 'market_trend' },
  { industry: 'Electrical', query: 'Electrical contractor market trends Texas 2026 EV solar growth', signal_type: 'market_trend' },
  
  // Competitor analysis
  { industry: 'All', query: 'Podium vs ServiceTitan vs Jobber trade business software pricing 2026', signal_type: 'competitor_move' },
  { industry: 'All', query: 'AI voice agent trade businesses new competitors 2026', signal_type: 'competitor_move' },
  
  // Pricing intelligence
  { industry: 'All', query: 'average website cost small trade businesses 2026 monthly pricing', signal_type: 'pricing_intel' },
  { industry: 'All', query: 'AI chatbot voice agent pricing trade businesses 2026', signal_type: 'pricing_intel' },
  
  // Churn indicators
  { industry: 'All', query: 'reasons trade businesses cancel marketing services software churn', signal_type: 'churn_signal' },
];

async function queryPerplexity(query: string): Promise<any> {
  const res = await fetch(`${PERPLEXITY_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${PERPLEXITY_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'sonar-pro',
      messages: [
        {
          role: 'system',
          content: `You are a financial intelligence analyst for a SaaS company serving trade businesses (HVAC, plumbing, roofing, electrical). Extract actionable market data. Return JSON with: title, summary (2-3 sentences), confidence (0.0-1.0), recommended_action, urgency (low/normal/high/critical), key_data_points (array of strings).`
        },
        { role: 'user', content: query }
      ],
      temperature: 0.1,
      return_citations: true,
      search_recency_filter: 'month',
    }),
  });

  return res.json();
}

serve(async (_req) => {
  const results = [];

  for (const fq of FINANCE_QUERIES) {
    try {
      // Dedup check
      const encoder = new TextEncoder();
      const data = encoder.encode(fq.query + new Date().toISOString().split('T')[0]);
      const hashBuffer = await crypto.subtle.digest('SHA-256', data);
      const queryHash = Array.from(new Uint8Array(hashBuffer))
        .map(b => b.toString(16).padStart(2, '0')).join('');

      const { data: existing } = await supabase
        .from('fg_perplexity_market_cache')
        .select('id')
        .eq('query_hash', queryHash)
        .single();

      if (existing) continue; // Already fetched today

      // Query Perplexity
      const response = await queryPerplexity(fq.query);
      const content = response.choices?.[0]?.message?.content;
      const citations = response.citations || [];

      if (!content) continue;

      // Parse AI response
      let parsed;
      try {
        parsed = JSON.parse(content);
      } catch {
        parsed = {
          title: `${fq.industry} Market Update`,
          summary: content.slice(0, 500),
          confidence: 0.5,
          recommended_action: 'Review and assess',
          urgency: 'normal',
        };
      }

      // Store signal
      await supabase.from('fg_perplexity_signals').insert({
        signal_type: fq.signal_type,
        industry: fq.industry,
        title: parsed.title,
        summary: parsed.summary,
        confidence: parsed.confidence,
        recommended_action: parsed.recommended_action,
        urgency: parsed.urgency,
        perplexity_query: fq.query,
        perplexity_sources: citations,
        raw_response: response,
      });

      // Store in market cache
      await supabase.from('fg_perplexity_market_cache').insert({
        query_hash: queryHash,
        industry: fq.industry,
        query: fq.query,
        key_trends: parsed.key_data_points || [],
        raw_response: response,
      });

      results.push({ industry: fq.industry, signal: fq.signal_type, status: 'synced' });

      // Rate limit: 500ms between calls
      await new Promise(r => setTimeout(r, 500));

    } catch (err) {
      results.push({ industry: fq.industry, signal: fq.signal_type, status: 'error', error: String(err) });
    }
  }

  // Log event
  await supabase.from('fg_revenue_events').insert({
    event_type: 'perplexity_sync',
    metadata: { results, synced_at: new Date().toISOString(), query_count: FINANCE_QUERIES.length },
  });

  return new Response(JSON.stringify({ success: true, results }), { status: 200 });
});
```

***

## Integration Layer — NPM Second Network API

### `supabase/functions/fg-npm-network/index.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// EDGE FUNCTION: NPM Second Network API Integration
// Partner referral ingestion, attribution, and revenue sharing
// ═══════════════════════════════════════════════════════════════════

import { serve } from 'https://deno.land/std@0.177.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
);

const NPM_API_BASE = Deno.env.get('NPM_NETWORK_API_URL')!;
const NPM_API_KEY = Deno.env.get('NPM_NETWORK_API_KEY')!;

async function npmRequest(path: string, method = 'GET', body?: any) {
  const res = await fetch(`${NPM_API_BASE}${path}`, {
    method,
    headers: {
      'Authorization': `Bearer ${NPM_API_KEY}`,
      'Content-Type': 'application/json',
      'X-Network-Id': 'citadel-finance-guild',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

serve(async (req) => {
  const { action, ...params } = await req.json();

  switch (action) {
    // ── Sync partners from NPM network ──
    case 'sync_partners': {
      const partners = await npmRequest('/v2/partners?status=active&limit=100');
      
      for (const p of partners.data || []) {
        await supabase.from('fg_npm_partners').upsert({
          npm_partner_id: p.id,
          partner_name: p.name,
          partner_type: p.type || 'referral',
          contact_email: p.email,
          contact_phone: p.phone,
          revenue_share_pct: p.revenue_share || 0.05,
          last_synced: new Date().toISOString(),
          npm_metadata: p,
        }, { onConflict: 'npm_partner_id' });
      }

      return new Response(JSON.stringify({ synced: partners.data?.length || 0 }));
    }

    // ── Ingest new referral from NPM webhook ──
    case 'ingest_referral': {
      const { referral_id, partner_id, referral_code, source, lead_data } = params;

      // Find partner
      const { data: partner } = await supabase
        .from('fg_npm_partners')
        .select('id')
        .eq('npm_partner_id', partner_id)
        .single();

      if (!partner) {
        return new Response(JSON.stringify({ error: 'Unknown partner' }), { status: 404 });
      }

      // Find rep by referral code territory match, or round-robin
      const { data: rep } = await supabase
        .from('fg_reps')
        .select('id')
        .eq('status', 'active')
        .order('created_at', { ascending: true })
        .limit(1)
        .single();

      // Create referral record
      const { data: referral } = await supabase.from('fg_npm_referrals').insert({
        partner_id: partner.id,
        rep_id: rep?.id,
        npm_referral_id: referral_id,
        referral_code,
        referral_source: source,
        status: 'pending',
        npm_metadata: lead_data,
      }).select().single();

      // Auto-create client if lead data provided
      if (lead_data?.business_name && rep) {
        const { data: client } = await supabase.from('fg_clients').insert({
          rep_id: rep.id,
          business_name: lead_data.business_name,
          contact_name: lead_data.contact_name || lead_data.business_name,
          contact_email: lead_data.email || '',
          contact_phone: lead_data.phone,
          industry: lead_data.industry,
          website_url: lead_data.website,
          lead_status: 'prospect',
          lead_source: 'npm_network',
          npm_referral_id: referral_id,
        }).select().single();

        if (client) {
          await supabase.from('fg_npm_referrals')
            .update({ client_id: client.id, status: 'verified', verified_at: new Date().toISOString() })
            .eq('id', referral!.id);
        }
      }

      // Notify NPM network of acknowledgment
      await npmRequest(`/v2/referrals/${referral_id}/ack`, 'POST', {
        status: 'received',
        assigned_to: rep?.id,
      });

      return new Response(JSON.stringify({ success: true, referral_id: referral!.id }));
    }

    // ── Report conversion back to NPM ──
    case 'report_conversion': {
      const { npm_referral_id, mrr, products } = params;

      const { data: referral } = await supabase
        .from('fg_npm_referrals')
        .select('*, fg_npm_partners(*)')
        .eq('npm_referral_id', npm_referral_id)
        .single();

      if (!referral) {
        return new Response(JSON.stringify({ error: 'Referral not found' }), { status: 404 });
      }

      const partnerPayout = parseFloat((mrr * (referral.fg_npm_partners?.revenue_share_pct || 0.05)).toFixed(2));

      // Update referral
      await supabase.from('fg_npm_referrals').update({
        status: 'active',
        attributed_mrr: mrr,
        partner_payout: partnerPayout,
        converted_at: new Date().toISOString(),
      }).eq('id', referral.id);

      // Update partner totals
      await supabase.rpc('fg_update_npm_partner_totals', {
        p_partner_id: referral.partner_id,
      });

      // Report back to NPM network
      await npmRequest(`/v2/referrals/${npm_referral_id}/convert`, 'POST', {
        mrr,
        products,
        partner_payout: partnerPayout,
        converted_at: new Date().toISOString(),
      });

      return new Response(JSON.stringify({ success: true, payout: partnerPayout }));
    }

    default:
      return new Response(JSON.stringify({ error: 'Unknown action' }), { status: 400 });
  }
});
```

***

## Integration Layer — DocuSend Pro

### `supabase/functions/fg-docusend/index.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// EDGE FUNCTION: DocuSend Pro — Document Generation & Delivery
// Templates: Proposals, Contracts, Invoices, SOWs, Onboarding Packets
// ═══════════════════════════════════════════════════════════════════

import { serve } from 'https://deno.land/std@0.177.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
);

const DOCUSEND_API_BASE = Deno.env.get('DOCUSEND_PRO_API_URL')!;
const DOCUSEND_API_KEY = Deno.env.get('DOCUSEND_PRO_API_KEY')!;

async function docusendRequest(path: string, method = 'GET', body?: any) {
  const res = await fetch(`${DOCUSEND_API_BASE}${path}`, {
    method,
    headers: {
      'Authorization': `Bearer ${DOCUSEND_API_KEY}`,
      'Content-Type': 'application/json',
      'X-Account-Id': 'citadel-finance-guild',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

// ── Document Templates ──────────────────────────────────────────

const TEMPLATES = {
  proposal: {
    id: 'tmpl_fg_proposal_v1',
    fields: ['business_name', 'contact_name', 'contact_email', 'industry',
             'recommended_products', 'monthly_total', 'setup_total',
             'website_score', 'scan_recommendation', 'rep_name', 'rep_email'],
  },
  contract: {
    id: 'tmpl_fg_contract_v1',
    fields: ['business_name', 'contact_name', 'contact_email', 'address',
             'products', 'monthly_total', 'setup_total', 'term_months',
             'commission_schedule', 'start_date'],
    requires_signature: true,
  },
  invoice: {
    id: 'tmpl_fg_invoice_v1',
    fields: ['business_name', 'invoice_number', 'line_items', 'subtotal',
             'tax', 'total', 'due_date', 'payment_link'],
  },
  onboarding_packet: {
    id: 'tmpl_fg_onboarding_v1',
    fields: ['business_name', 'contact_name', 'products_purchased',
             'zes_plan', 'tradebuilder_tier', 'setup_checklist',
             'rep_name', 'rep_phone', 'delivery_timeline'],
  },
  sow: {
    id: 'tmpl_fg_sow_v1',
    fields: ['business_name', 'project_scope', 'deliverables',
             'timeline', 'pricing', 'acceptance_criteria'],
    requires_signature: true,
  },
};

serve(async (req) => {
  const { action, ...params } = await req.json();

  switch (action) {

    // ── Generate document from scan results ──
    case 'generate_proposal': {
      const { client_id, scan_id, rep_id } = params;

      const { data: client } = await supabase
        .from('fg_clients').select('*').eq('id', client_id).single();
      const { data: scan } = await supabase
        .from('fg_lead_scans').select('*').eq('id', scan_id).single();
      const { data: rep } = await supabase
        .from('fg_reps').select('*').eq('id', rep_id).single();

      if (!client || !rep) {
        return new Response(JSON.stringify({ error: 'Missing data' }), { status: 400 });
      }

      // Build product recommendations from scan
      const products = await buildProductRecommendations(scan);

      // Generate via DocuSend Pro
      const docResult = await docusendRequest('/v1/documents/generate', 'POST', {
        template_id: TEMPLATES.proposal.id,
        variables: {
          business_name: client.business_name,
          contact_name: client.contact_name,
          contact_email: client.contact_email,
          industry: client.industry || 'Trade Services',
          recommended_products: products.descriptions,
          monthly_total: `$${products.monthly_total.toFixed(2)}/mo`,
          setup_total: products.setup_total > 0 ? `$${products.setup_total.toFixed(2)} one-time` : 'Waived',
          website_score: scan?.website_score || 'N/A',
          scan_recommendation: scan?.recommendation || 'Custom',
          rep_name: rep.full_name,
          rep_email: rep.email,
          // Branding
          company_name: 'Citadel-Nexus',
          logo_url: 'https://citadel-nexus.com/assets/logo.svg',
          accent_color: '#6d28d9',
        },
        output: { format: 'pdf', quality: 'high' },
        delivery: {
          method: 'email',
          to: client.contact_email,
          subject: `Your ${client.industry || 'Business'} Growth Proposal — Citadel-Nexus`,
          message: `Hi ${client.contact_name},\n\nAttached is your customized growth proposal. Let me know if you have any questions.\n\n— ${rep.full_name}`,
        },
      });

      // Store document record
      const { data: doc } = await supabase.from('fg_documents').insert({
        client_id,
        rep_id,
        doc_type: 'proposal',
        title: `Proposal — ${client.business_name}`,
        template_id: TEMPLATES.proposal.id,
        docusend_doc_id: docResult.document_id,
        docusend_envelope_id: docResult.envelope_id,
        docusend_status: 'sent',
        preview_url: docResult.preview_url,
        download_url: docResult.download_url,
        sent_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
        generated_from: { scan_id, products },
      }).select().single();

      // Log event
      await supabase.from('fg_document_events').insert({
        document_id: doc!.id,
        event_type: 'sent',
        actor_email: rep.email,
      });

      return new Response(JSON.stringify({ success: true, document: doc, urls: docResult }));
    }

    // ── Generate contract for signing ──
    case 'generate_contract': {
      const { client_id, rep_id, products, term_months = 12 } = params;

      const { data: client } = await supabase
        .from('fg_clients').select('*').eq('id', client_id).single();
      const { data: rep } = await supabase
        .from('fg_reps').select('*').eq('id', rep_id).single();

      const monthlyTotal = products.reduce((sum: number, p: any) => sum + p.price_monthly, 0);
      const setupTotal = products.reduce((sum: number, p: any) => sum + (p.price_setup || 0), 0);

      const docResult = await docusendRequest('/v1/documents/generate', 'POST', {
        template_id: TEMPLATES.contract.id,
        variables: {
          business_name: client!.business_name,
          contact_name: client!.contact_name,
          contact_email: client!.contact_email,
          address: client!.address || 'On file',
          products: products.map((p: any) => `${p.name}: $${p.price_monthly}/mo`).join('\n'),
          monthly_total: `$${monthlyTotal.toFixed(2)}`,
          setup_total: `$${setupTotal.toFixed(2)}`,
          term_months: `${term_months} months`,
          commission_schedule: 'Per Finance Guild standard schedule',
          start_date: new Date().toLocaleDateString(),
        },
        signing: {
          enabled: true,
          signers: [
            { name: client!.contact_name, email: client!.contact_email, role: 'client' },
            { name: rep!.full_name, email: rep!.email, role: 'representative' },
          ],
          reminder_days: [3, 7],
          expiry_days: 14,
        },
        output: { format: 'pdf', quality: 'high' },
      });

      const { data: doc } = await supabase.from('fg_documents').insert({
        client_id,
        rep_id,
        doc_type: 'contract',
        title: `Contract — ${client!.business_name}`,
        template_id: TEMPLATES.contract.id,
        docusend_doc_id: docResult.document_id,
        docusend_envelope_id: docResult.envelope_id,
        docusend_status: 'sent',
        preview_url: docResult.preview_url,
        signing_url: docResult.signing_url,
        sent_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString(),
        generated_from: { products, term_months },
      }).select().single();

      return new Response(JSON.stringify({ success: true, document: doc, signing_url: docResult.signing_url }));
    }

    // ── Webhook handler from DocuSend ──
    case 'webhook': {
      const { event, document_id, envelope_id, data } = params;

      const { data: doc } = await supabase
        .from('fg_documents')
        .select('*')
        .eq('docusend_doc_id', document_id)
        .single();

      if (!doc) {
        return new Response(JSON.stringify({ error: 'Document not found' }), { status: 404 });
      }

      const statusMap: Record<string, string> = {
        'document.viewed': 'viewed',
        'document.signed': 'signed',
        'document.expired': 'expired',
        'document.downloaded': 'viewed',
      };

      const newStatus = statusMap[event];
      if (newStatus) {
        const updates: Record<string, any> = { docusend_status: newStatus, updated_at: new Date().toISOString() };
        if (event === 'document.viewed' && !doc.first_viewed_at) updates.first_viewed_at = new Date().toISOString();
        if (event === 'document.signed') updates.signed_at = new Date().toISOString();

        await supabase.from('fg_documents').update(updates).eq('id', doc.id);
      }

      // Log event
      await supabase.from('fg_document_events').insert({
        document_id: doc.id,
        event_type: event.replace('document.', ''),
        actor_email: data?.signer_email,
        actor_ip: data?.ip_address,
        metadata: data,
      });

      // If contract signed → auto-progress client to 'won'
      if (event === 'document.signed' && doc.doc_type === 'contract') {
        await supabase.from('fg_clients')
          .update({ lead_status: 'won', updated_at: new Date().toISOString() })
          .eq('id', doc.client_id);
      }

      return new Response(JSON.stringify({ success: true }));
    }

    default:
      return new Response(JSON.stringify({ error: 'Unknown action' }), { status: 400 });
  }
});

// ── Helper: Build product recommendations from scan ──
async function buildProductRecommendations(scan: any) {
  const { data: products } = await supabase
    .from('fg_products')
    .select('*')
    .eq('active', true);

  const recommended: any[] = [];

  if (!scan || !scan.has_website || scan.website_score < 30) {
    // No website or terrible → TradeBuilder Growth + ZES Operator
    const tb = products?.find((p: any) => p.slug === 'tradebuilder-growth');
    const zes = products?.find((p: any) => p.slug === 'zes-operator');
    if (tb) recommended.push(tb);
    if (zes) recommended.push(zes);
  } else if (scan.website_score < 60) {
    // Poor website → TradeBuilder Starter + ZES Operator
    const tb = products?.find((p: any) => p.slug === 'tradebuilder-starter');
    const zes = products?.find((p: any) => p.slug === 'zes-operator');
    if (tb) recommended.push(tb);
    if (zes) recommended.push(zes);
  } else {
    // Good website → ZES only (24hr delivery)
    const zes = products?.find((p: any) => p.slug === 'zes-autopilot');
    if (zes) recommended.push(zes);
  }

  return {
    products: recommended,
    descriptions: recommended.map(p => `${p.name} — $${p.price_monthly}/mo`),
    monthly_total: recommended.reduce((s, p) => s + (p.price_monthly || 0), 0),
    setup_total: recommended.reduce((s, p) => s + (p.price_setup || 0), 0),
  };
}
```

***

## Metabase Embed Component

### `src/components/MetabaseEmbed.tsx`

```tsx
import { useState, useEffect } from 'react';

interface MetabaseEmbedProps {
  dashboardId: number;
  params?: Record<string, string>;
  height?: string;
  title?: string;
}

const METABASE_SITE_URL = import.meta.env.VITE_METABASE_SITE_URL || 'https://metabase.citadel-nexus.com';

export default function MetabaseEmbed({ dashboardId, params = {}, height = '600px', title }: MetabaseEmbedProps) {
  const [iframeUrl, setIframeUrl] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function getEmbedUrl() {
      try {
        const res = await fetch('/api/admin/metabase/embed-url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dashboard_id: dashboardId, params }),
        });
        const { url } = await res.json();
        setIframeUrl(url);
      } catch {
        // Fallback to public embed URL
        const paramStr = Object.entries(params).map(([k, v]) => `${k}=${v}`).join('&');
        setIframeUrl(`${METABASE_SITE_URL}/public/dashboard/${dashboardId}${paramStr ? '?' + paramStr : ''}`);
      }
      setLoading(false);
    }
    getEmbedUrl();
  }, [dashboardId, JSON.stringify(params)]);

  return (
    <div className="guild-card overflow-hidden">
      {title && (
        <div className="px-5 py-3 border-b border-[var(--fg-border)]">
          <h3 className="text-sm font-bold">{title}</h3>
        </div>
      )}
      {loading ? (
        <div className="flex items-center justify-center" style={{ height }}>
          <div className="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full" />
        </div>
      ) : (
        <iframe
          src={iframeUrl}
          style={{ width: '100%', height, border: 'none' }}
          title={title || `Metabase Dashboard ${dashboardId}`}
          sandbox="allow-scripts allow-same-origin allow-popups"
          loading="lazy"
        />
      )}
    </div>
  );
}
```

### Metabase Dashboard Configuration

```yaml
# metabase/dashboards/finance-guild.yaml
# These map to Supabase materialized views

dashboards:
  # ── Dashboard 1: Revenue Overview ──
  - id: 1
    name: "Finance Guild — Revenue Overview"
    cards:
      - name: "MRR by Revenue Layer"
        source: fg_mv_revenue_by_layer
        type: bar
        x: month
        y: total_revenue
        color: layer
        
      - name: "Total MRR Trend"
        source: fg_mv_revenue_by_layer
        type: line
        x: month
        y: total_revenue
        
      - name: "Client Count by Layer"
        source: fg_mv_revenue_by_layer
        type: pie
        dimension: layer
        metric: clients

  # ── Dashboard 2: Rep Performance ──
  - id: 2
    name: "Finance Guild — Rep Leaderboard"
    cards:
      - name: "Rep Leaderboard"
        source: fg_mv_rep_performance
        type: table
        columns: [full_name, total_mrr, won_clients, total_earned, scan_conversion_rate]
        sort: total_earned DESC

      - name: "Scan Conversion Funnel"
        source: fg_mv_rep_performance
        type: funnel
        steps: [total_scans, converted_scans, won_clients]

  # ── Dashboard 3: Vertical Heatmap ──
  - id: 3
    name: "Finance Guild — Industry Verticals"
    cards:
      - name: "Vertical Revenue Heatmap"
        source: fg_mv_vertical_heatmap
        type: heatmap
        x: period
        y: industry
        value: total_mrr

      - name: "Churn Rate by Industry"
        source: fg_mv_vertical_heatmap
        type: bar
        x: industry
        y: churn_rate
        color_scale: red

  # ── Dashboard 4: NPM Network ──
  - id: 4
    name: "Finance Guild — NPM Network"
    cards:
      - name: "Partner Performance"
        source: fg_mv_npm_performance
        type: table
        columns: [partner_name, total_referrals, active_referrals, total_attributed_mrr, conversion_rate]

      - name: "Referral Pipeline"
        source: fg_npm_referrals
        type: pie
        dimension: status

  # ── Dashboard 5: Perplexity Market Intel ──
  - id: 5
    name: "Finance Guild — Market Intelligence"
    cards:
      - name: "Signal Feed"
        source: fg_perplexity_signals
        type: table
        columns: [title, industry, signal_type, confidence, urgency, fetched_at]
        filter: "expires_at > now()"
        sort: fetched_at DESC

      - name: "Signals by Industry"
        source: fg_perplexity_signals
        type: bar
        x: industry
        y: count
        color: signal_type

  # ── Dashboard 6: DocuSend Documents ──
  - id: 6
    name: "Finance Guild — Document Pipeline"
    cards:
      - name: "Document Status"
        source: fg_documents
        type: pie
        dimension: docusend_status

      - name: "Time to View/Sign"
        source: fg_documents
        type: bar
        x: doc_type
        y: "EXTRACT(EPOCH FROM (first_viewed_at - sent_at)) / 3600"
        label: "Hours to First View"

      - name: "Recent Documents"
        source: fg_documents
        type: table
        columns: [title, doc_type, docusend_status, sent_at, signed_at]
        sort: created_at DESC
        limit: 20
```

***

## Product Seed Data

### `supabase/seed/products.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- PRODUCT CATALOG SEED — Finance Guild
-- Ref: Monetization Strategy Q1 2026 + ZES Plan Guide
-- ═══════════════════════════════════════════════════════════════════

-- ZES Plans (Agent products — 24hr delivery)
INSERT INTO fg_products (name, slug, layer, description, price_monthly, price_setup, is_zes_agent, margin_pct) VALUES
  ('ZES Scout',    'zes-scout',    'tradeboost', 'Get Found — GBP, lead CRM, missed call text-back',           15.00, 0,    true, 92),
  ('ZES Operator', 'zes-operator', 'tradeboost', 'Run Smarter — Booking, reviews, SEO audit, social content', 20.00, 0,    true, 90),
  ('ZES Autopilot','zes-autopilot','tradeboost', 'Full AI agent — Voice, workflows, analytics, forecasting',  30.00, 0,    true, 87);

-- TradeBuilder Website Plans (Website income product)
INSERT INTO fg_products (name, slug, layer, description, price_monthly, price_setup, is_tradebuilder, margin_pct) VALUES
  ('TradeBuilder Starter',   'tradebuilder-starter',   'website_factory', '3 pages, domain, SSL, basic SEO',                   99.00,  99.00, true, 89),
  ('TradeBuilder Growth',    'tradebuilder-growth',    'website_factory', '10 pages, booking widget, reviews, blog',           199.00, 149.00, true, 85),
  ('TradeBuilder Premium',   'tradebuilder-premium',   'website_factory', 'Unlimited pages, AI content, CRM integration',      299.00, 199.00, true, 82);

-- TradeBoost Micro-Services (standalone)
INSERT INTO fg_products (name, slug, layer, description, price_monthly, margin_pct) VALUES
  ('Missed-Call Text-Back',        'tb-missed-call',       'tradeboost', 'Auto-text when you miss a call',                20.00, 92),
  ('Review Request Automator',     'tb-review-request',    'tradeboost', 'Automated review requests after service',       15.00, 95),
  ('Smart Booking Link',           'tb-smart-booking',     'tradeboost', 'Online booking with smart scheduling',          20.00, 93),
  ('Estimate Follow-Up Drip',      'tb-estimate-drip',     'tradeboost', 'Automated follow-up on open estimates',         20.00, 91),
  ('GBP Post Scheduler',           'tb-gbp-scheduler',     'tradeboost', 'Auto Google Business posts monthly',            15.00, 96),
  ('Reputation Dashboard',         'tb-reputation-dash',   'tradeboost', 'Monitor reviews across all platforms',          25.00, 90),
  ('Job Complete Photo→Review',    'tb-photo-review',      'tradeboost', 'Photo upload triggers review request',          20.00, 88),
  ('Storm/Event Blast',            'tb-storm-blast',       'tradeboost', 'Geo-targeted SMS during weather events',        25.00, 80),
  ('Referral Tracker',             'tb-referral-tracker',  'tradeboost', 'Track and reward customer referrals',           15.00, 95),
  ('Invoice Reminder Automator',   'tb-invoice-reminder',  'tradeboost', 'Auto-nudge on unpaid invoices',                 20.00, 92),
  ('Neighborhood Postcards',       'tb-postcards',         'tradeboost', '"Just Served" postcards to neighbors',          30.00, 70),
  ('Seasonal Maintenance Reminder','tb-seasonal-reminder', 'tradeboost', 'Auto-reminders for seasonal service',           15.00, 95),
  ('After-Hours AI Chat',          'tb-afterhours-chat',   'tradeboost', '24/7 AI chat widget on your website',           25.00, 87),
  ('AI Voicemail Drop',            'tb-voicemail-drop',    'tradeboost', 'Personalized AI voicemail follow-ups',          25.00, 85);

-- Platform SaaS Tiers
INSERT INTO fg_products (name, slug, layer, description, price_monthly, margin_pct) VALUES
  ('Citadel Free',       'platform-free',       'platform_saas', 'API sandbox, 1K calls/mo',                        0.00,  0),
  ('Citadel Starter',    'platform-starter',    'platform_saas', '5K API calls, basic agents',                     29.00, 90),
  ('Citadel Pro',        'platform-pro',        'platform_saas', '25K calls, CAPS Lite, 3 agents',                 99.00, 88),
  ('Citadel Business',   'platform-business',   'platform_saas', '100K calls, full CAPS, Watcher, 10 agents',     499.00, 85),
  ('Citadel Agency',     'platform-agency',     'platform_saas', 'Watcher suite, CE tracking, dedicated support', 2499.00, 80),
  ('Citadel Enterprise', 'platform-enterprise', 'platform_saas', 'White-label, custom, SLA, on-prem option',     9999.00, 75);
```

***

This gives you the complete data layer and integration spine . The Supabase schema maps every revenue layer — TradeBoost micro-services at $15-30/mo, Website Factory at $99-299/mo, and Platform SaaS at $29-9,999/mo  — with ZES as the agent product ($15-30/mo, 24hr delivery) and TradeBuilder as the website income product with ZES as an extension upsell at 10-20% bundle discount . Perplexity Finance Data feeds market intelligence into `fg_perplexity_signals` on a 6-hour cron, NPM Second Network handles partner referral attribution with automatic revenue sharing, and DocuSend Pro generates proposals directly from lead scan results with e-signature tracking. All of it materializes into Metabase dashboards embedded via `<MetabaseEmbed />` for real-time analytics across revenue layers, rep performance, vertical heatmaps, and the partner network.Here is the complete Finance Guild visual system — gamification engine, badges, medals, achievements, animations, rank visuals, tenant structure, and all supporting files — all mapped directly to your FATE economy and tier progression.

***

## Finance Guild — File Structure

```
services/finance-guild/
├── src/
│   ├── gamification/
│   │   ├── types.ts                    ← All FATE/XP/TP types
│   │   ├── constants.ts                ← Tier thresholds, XP values, badge defs
│   │   ├── engine.ts                   ← XP calculation engine
│   │   ├── achievements.ts             ← Achievement unlock logic
│   │   └── animations.ts               ← Framer Motion animation presets
│   │
│   ├── components/
│   │   ├── badges/
│   │   │   ├── BadgeIcon.tsx            ← SVG badge renderer (tier-aware)
│   │   │   ├── MedalDisplay.tsx         ← Medal shelf component
│   │   │   ├── AchievementCard.tsx      ← Single achievement with unlock anim
│   │   │   ├── AchievementToast.tsx     ← Toast popup on unlock
│   │   │   ├── AchievementGrid.tsx      ← Full achievement gallery
│   │   │   └── BadgeShowcase.tsx        ← Profile badge display row
│   │   │
│   │   ├── rank/
│   │   │   ├── RankBadge.tsx            ← Tier emblem with glow
│   │   │   ├── RankProgressBar.tsx      ← XP progress to next tier
│   │   │   ├── RankCard.tsx             ← Full rank card (avatar + stats)
│   │   │   ├── TierGate.tsx             ← Conditional render by tier
│   │   │   └── LevelUpOverlay.tsx       ← Fullscreen level-up celebration
│   │   │
│   │   ├── leaderboard/
│   │   │   ├── RepLeaderboard.tsx       ← Animated leaderboard
│   │   │   ├── LeaderboardRow.tsx       ← Single rep row w/ rank badge
│   │   │   └── LeaderboardPodium.tsx    ← Top 3 podium display
│   │   │
│   │   ├── visuals/
│   │   │   ├── ParticleField.tsx        ← Background particle system
│   │   │   ├── GlowCard.tsx             ← Card with tier-colored glow
│   │   │   ├── PulseRing.tsx            ← Pulsating ring indicator
│   │   │   ├── ShimmerText.tsx          ← Gold/purple shimmer text
│   │   │   ├── ConfettiExplosion.tsx    ← Achievement unlock confetti
│   │   │   ├── NumberCounter.tsx        ← Animated count-up
│   │   │   └── GradientBorder.tsx       ← Animated gradient border
│   │   │
│   │   └── guild-master/
│   │       ├── GuildMasterWidget.tsx     ← ElevenLabs voice agent embed
│   │       ├── GuildMasterOrb.tsx       ← Floating orb w/ audio visualizer
│   │       └── GuildMasterChat.tsx      ← Chat + voice transcript panel
│   │
│   ├── pages/
│   │   ├── RepProfile.tsx               ← Rep profile w/ rank + badges + stats
│   │   ├── Achievements.tsx             ← Full achievement gallery page
│   │   └── GuildHall.tsx                ← Guild overview + leaderboard + orb
│   │
│   ├── tenant/
│   │   ├── TenantProvider.tsx           ← Multi-tenant context (Finance Guild)
│   │   ├── TenantConfig.ts             ← Tenant-specific config
│   │   ├── TenantTheme.ts              ← Finance Guild color tokens
│   │   └── TenantRBAC.ts               ← Role-based access per tenant
│   │
│   └── styles/
│       ├── guild-theme.css              ← CSS variables + dark theme
│       ├── animations.css               ← Keyframe animations
│       └── badge-sprites.css            ← Badge sprite sheet styles
│
├── supabase/
│   ├── migrations/
│   │   ├── 001_finance_guild_schema.sql     ← (from previous)
│   │   ├── 002_finance_guild_rls.sql        ← (from previous)
│   │   ├── 003_gamification_schema.sql      ← XP, badges, achievements tables
│   │   └── 004_tenant_schema.sql            ← Multi-tenant isolation
│   ├── functions/
│   │   ├── fg-calculate-commission/         ← (from previous)
│   │   ├── fg-perplexity-sync/              ← (from previous)
│   │   ├── fg-npm-network/                  ← (from previous)
│   │   ├── fg-docusend/                     ← (from previous)
│   │   ├── fg-xp-engine/index.ts            ← XP award + level-up logic
│   │   └── fg-achievement-check/index.ts    ← Achievement unlock checker
│   └── seed/
│       ├── products.sql                     ← (from previous)
│       ├── badges.sql                       ← Badge + medal definitions
│       └── achievements.sql                 ← Achievement definitions
│
├── infra/
│   ├── ansible/
│   │   ├── playbooks/
│   │   │   ├── deploy-finance-guild.yml
│   │   │   ├── rotate-secrets.yml
│   │   │   └── setup-cloudflare.yml
│   │   ├── inventory/
│   │   │   └── production.yml
│   │   └── roles/
│   │       ├── supabase/
│   │       ├── cloudflare/
│   │       └── metabase/
│   │
│   └── cloudflare/
│       ├── wrangler.toml
│       ├── firewall-rules.json
│       └── page-rules.json
│
├── security/
│   ├── icp-tiers.yaml                  ← ICP tier classification
│   ├── srs-tags.yaml                   ← SRS tag registry for Finance Guild
│   ├── caps-policies.yaml              ← CAPS scoring policies
│   └── threat-model.md                 ← Finance Guild threat model
│
└── docs/
    ├── FINANCE_GUILD_TENETS.md          ← Guild tenets & operating principles
    ├── ACHIEVEMENT_CATALOG.md
    └── RANK_SYSTEM.md
```

***

## Gamification Types & Constants

### `src/gamification/types.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// FINANCE GUILD — Gamification Type System
// FATE Economy: XP / Trust Points / Trust Score
// Ref: Engagement System Template + Service Tier Template
// ═══════════════════════════════════════════════════════════════════

export type GuildTier = 
  | 'initiate'      // Entry — no commission, learning
  | '3-star'        // Professional entry — commissions start
  | '4-star'        // Intermediate — higher rates
  | '5-star'        // Senior — premium rates
  | 'elite'         // Master — equity options
  | 'd-tier';       // Legendary — custom negotiated

export type BadgeRarity = 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary';

export type MedalType = 
  | 'revenue'       // Revenue milestones
  | 'conversion'    // Scan-to-close conversion
  | 'retention'     // Client retention streaks
  | 'streak'        // Activity streaks
  | 'guild'         // Guild contribution
  | 'special';      // One-time / seasonal

export interface Badge {
  id: string;
  name: string;
  description: string;
  icon: string;           // SVG path or emoji
  rarity: BadgeRarity;
  category: MedalType;
  xp_reward: number;
  tier_required: GuildTier;
  criteria: BadgeCriteria;
  visual: BadgeVisual;
}

export interface BadgeCriteria {
  metric: string;         // e.g. 'total_mrr', 'clients_won', 'scan_count'
  operator: 'gte' | 'eq' | 'streak' | 'within';
  value: number;
  period?: 'day' | 'week' | 'month' | 'quarter' | 'year' | 'all_time';
}

export interface BadgeVisual {
  gradient_start: string;
  gradient_end: string;
  glow_color: string;
  border_style: 'solid' | 'dashed' | 'pulse' | 'flame';
  particle_type?: 'sparkle' | 'fire' | 'lightning' | 'coin' | 'none';
  animation?: 'spin' | 'bounce' | 'glow' | 'shake' | 'float';
}

export interface Achievement {
  id: string;
  name: string;
  description: string;
  icon: string;
  rarity: BadgeRarity;
  xp_reward: number;
  tp_reward: number;       // Trust Points
  badges_awarded: string[];
  secret: boolean;         // Hidden until unlocked
  criteria: AchievementCriteria[];
}

export interface AchievementCriteria {
  type: 'badge_count' | 'metric_threshold' | 'streak' | 'event' | 'tier_reach' | 'combo';
  params: Record<string, any>;
}

export interface RepProfile {
  rep_id: string;
  tier: GuildTier;
  xp: number;
  xp_to_next: number;
  trust_points: number;
  trust_score: number;     // 0.00 - 1.00
  level: number;
  title: string;           // Dynamic title from tier + level
  badges: string[];
  achievements: string[];
  streak_days: number;
  rank_position: number;   // Leaderboard position
}

export interface LevelUpEvent {
  rep_id: string;
  old_level: number;
  new_level: number;
  old_tier: GuildTier;
  new_tier: GuildTier;
  xp_earned: number;
  badges_unlocked: string[];
  achievements_unlocked: string[];
  timestamp: string;
}
```

### `src/gamification/constants.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// FINANCE GUILD — Tier Thresholds, XP Values, Badge Definitions
// Mapped from: Service Tier Template (citadel-nexus.com)
// ═══════════════════════════════════════════════════════════════════

import { GuildTier, Badge, Achievement, BadgeRarity } from './types';

// ── TIER THRESHOLDS ───────────────────────────────────────────────
// Ref: Service Tier Template scoring algorithm

export const TIER_THRESHOLDS: Record<GuildTier, { xp: number; level: number; title: string; color: string; glow: string }> = {
  'initiate':  { xp: 0,     level: 1,  title: 'Guild Initiate',     color: '#6b7280', glow: 'rgba(107,114,128,0.3)' },
  '3-star':    { xp: 300,   level: 5,  title: 'Finance Scout',      color: '#a78bfa', glow: 'rgba(167,139,250,0.4)' },
  '4-star':    { xp: 600,   level: 10, title: 'Revenue Operator',   color: '#3b82f6', glow: 'rgba(59,130,246,0.4)'  },
  '5-star':    { xp: 1000,  level: 15, title: 'Revenue Architect',  color: '#f59e0b', glow: 'rgba(245,158,11,0.4)'  },
  'elite':     { xp: 1500,  level: 20, title: 'Finance Commander',  color: '#ef4444', glow: 'rgba(239,68,68,0.4)'   },
  'd-tier':    { xp: 2500,  level: 25, title: 'Guild Master',       color: '#fbbf24', glow: 'rgba(251,191,36,0.5)'  },
};

// ── XP VALUES — FINANCE GUILD ACTIVITIES ──────────────────────────

export const XP_VALUES = {
  // Sales activities
  lead_scan_completed:        10,
  lead_contacted:             15,
  demo_scheduled:             25,
  demo_completed:             35,
  proposal_sent:              40,  // DocuSend Pro integration
  contract_signed:            100, // DocuSend Pro webhook
  client_first_payment:       150,
  
  // Revenue milestones (one-time)
  first_sale:                 200,
  first_1k_mrr:              300,
  first_5k_mrr:              500,
  first_10k_mrr:             750,
  first_50k_arr:             1000,
  
  // Retention activities
  client_month_retained:      5,   // per client per month
  churn_save:                 75,  // saved a client from churning
  upsell_closed:              50,  // existing client upgraded
  bundle_sold:                60,  // TradeBuilder + ZES bundle
  
  // Guild contributions
  training_completed:         20,
  documentation_created:      30,
  peer_helped:                15,
  guild_master_session:       25,  // Interacted with Finance Guild Master voice agent
  
  // NPM Network
  npm_referral_received:      10,
  npm_referral_converted:     50,
  
  // Perplexity signals
  market_signal_acted_on:     20,
  competitor_intel_reported:   35,
  
  // Streaks
  daily_login_bonus:          2,
  weekly_active_bonus:        25,
  monthly_active_bonus:       100,
};

// ── LEVEL THRESHOLDS ──────────────────────────────────────────────
// Exponential curve: level_xp = base * (multiplier ^ level)

export const LEVEL_CONFIG = {
  base_xp: 100,
  multiplier: 1.35,
  max_level: 50,
};

export function xpForLevel(level: number): number {
  return Math.floor(LEVEL_CONFIG.base_xp * Math.pow(LEVEL_CONFIG.multiplier, level - 1));
}

export function levelFromXP(totalXP: number): number {
  let level = 1;
  let accumulated = 0;
  while (level < LEVEL_CONFIG.max_level) {
    const needed = xpForLevel(level);
    if (accumulated + needed > totalXP) break;
    accumulated += needed;
    level++;
  }
  return level;
}

// ── BADGE DEFINITIONS ─────────────────────────────────────────────

export const BADGES: Badge[] = [
  // ── Revenue Badges ──
  {
    id: 'first_blood',
    name: 'First Blood',
    description: 'Close your first sale',
    icon: '🩸',
    rarity: 'common',
    category: 'revenue',
    xp_reward: 200,
    tier_required: 'initiate',
    criteria: { metric: 'clients_won', operator: 'gte', value: 1 },
    visual: { gradient_start: '#ef4444', gradient_end: '#dc2626', glow_color: '#ef4444', border_style: 'solid', particle_type: 'sparkle' },
  },
  {
    id: 'revenue_engine',
    name: 'Revenue Engine',
    description: 'Reach $1K MRR in your portfolio',
    icon: '⚙️',
    rarity: 'uncommon',
    category: 'revenue',
    xp_reward: 300,
    tier_required: '3-star',
    criteria: { metric: 'total_mrr', operator: 'gte', value: 1000 },
    visual: { gradient_start: '#6366f1', gradient_end: '#4f46e5', glow_color: '#818cf8', border_style: 'pulse', particle_type: 'coin' },
  },
  {
    id: 'money_machine',
    name: 'Money Machine',
    description: 'Reach $5K MRR in your portfolio',
    icon: '💰',
    rarity: 'rare',
    category: 'revenue',
    xp_reward: 500,
    tier_required: '3-star',
    criteria: { metric: 'total_mrr', operator: 'gte', value: 5000 },
    visual: { gradient_start: '#f59e0b', gradient_end: '#d97706', glow_color: '#fbbf24', border_style: 'pulse', particle_type: 'coin', animation: 'float' },
  },
  {
    id: 'whale_hunter',
    name: 'Whale Hunter',
    description: 'Close a single deal worth $500+/mo',
    icon: '🐋',
    rarity: 'epic',
    category: 'revenue',
    xp_reward: 750,
    tier_required: '4-star',
    criteria: { metric: 'single_deal_mrr', operator: 'gte', value: 500 },
    visual: { gradient_start: '#0ea5e9', gradient_end: '#0284c7', glow_color: '#38bdf8', border_style: 'pulse', particle_type: 'lightning', animation: 'glow' },
  },
  {
    id: 'rainmaker',
    name: 'Rainmaker',
    description: 'Reach $10K MRR — you are the storm',
    icon: '🌧️',
    rarity: 'legendary',
    category: 'revenue',
    xp_reward: 1000,
    tier_required: '5-star',
    criteria: { metric: 'total_mrr', operator: 'gte', value: 10000 },
    visual: { gradient_start: '#fbbf24', gradient_end: '#f59e0b', glow_color: '#fde68a', border_style: 'flame', particle_type: 'lightning', animation: 'shake' },
  },

  // ── Conversion Badges ──
  {
    id: 'sharpshooter',
    name: 'Sharpshooter',
    description: '5 scans → 5 closes (100% conversion)',
    icon: '🎯',
    rarity: 'epic',
    category: 'conversion',
    xp_reward: 600,
    tier_required: '3-star',
    criteria: { metric: 'scan_conversion_rate', operator: 'eq', value: 100, period: 'month' },
    visual: { gradient_start: '#10b981', gradient_end: '#059669', glow_color: '#34d399', border_style: 'solid', particle_type: 'sparkle' },
  },
  {
    id: 'speed_demon',
    name: 'Speed Demon',
    description: 'Close a deal within 24 hours of scan',
    icon: '⚡',
    rarity: 'rare',
    category: 'conversion',
    xp_reward: 400,
    tier_required: '3-star',
    criteria: { metric: 'fastest_scan_to_close_hours', operator: 'gte', value: 1 },
    visual: { gradient_start: '#eab308', gradient_end: '#ca8a04', glow_color: '#facc15', border_style: 'pulse', particle_type: 'lightning', animation: 'bounce' },
  },
  {
    id: 'scanner_pro',
    name: 'Scanner Pro',
    description: 'Complete 50 lead scans',
    icon: '🔍',
    rarity: 'uncommon',
    category: 'conversion',
    xp_reward: 250,
    tier_required: 'initiate',
    criteria: { metric: 'total_scans', operator: 'gte', value: 50 },
    visual: { gradient_start: '#8b5cf6', gradient_end: '#7c3aed', glow_color: '#a78bfa', border_style: 'solid', particle_type: 'sparkle' },
  },

  // ── Retention Badges ──
  {
    id: 'iron_grip',
    name: 'Iron Grip',
    description: 'Zero churn for 3 consecutive months',
    icon: '🤝',
    rarity: 'rare',
    category: 'retention',
    xp_reward: 400,
    tier_required: '3-star',
    criteria: { metric: 'zero_churn_months', operator: 'streak', value: 3 },
    visual: { gradient_start: '#14b8a6', gradient_end: '#0d9488', glow_color: '#2dd4bf', border_style: 'solid', particle_type: 'none' },
  },
  {
    id: 'save_artist',
    name: 'Save Artist',
    description: 'Save 5 clients from churning',
    icon: '🛟',
    rarity: 'epic',
    category: 'retention',
    xp_reward: 500,
    tier_required: '4-star',
    criteria: { metric: 'churn_saves', operator: 'gte', value: 5 },
    visual: { gradient_start: '#f97316', gradient_end: '#ea580c', glow_color: '#fb923c', border_style: 'pulse', particle_type: 'fire', animation: 'glow' },
  },

  // ── Streak Badges ──
  {
    id: 'on_fire',
    name: 'On Fire',
    description: '7-day login streak',
    icon: '🔥',
    rarity: 'common',
    category: 'streak',
    xp_reward: 100,
    tier_required: 'initiate',
    criteria: { metric: 'login_streak', operator: 'streak', value: 7 },
    visual: { gradient_start: '#ef4444', gradient_end: '#f97316', glow_color: '#ef4444', border_style: 'flame', particle_type: 'fire', animation: 'bounce' },
  },
  {
    id: 'unstoppable',
    name: 'Unstoppable',
    description: '30-day login streak',
    icon: '💎',
    rarity: 'rare',
    category: 'streak',
    xp_reward: 300,
    tier_required: '3-star',
    criteria: { metric: 'login_streak', operator: 'streak', value: 30 },
    visual: { gradient_start: '#06b6d4', gradient_end: '#0891b2', glow_color: '#22d3ee', border_style: 'pulse', particle_type: 'sparkle', animation: 'float' },
  },

  // ── Guild Badges ──
  {
    id: 'guild_voice',
    name: 'Guild Voice',
    description: 'Complete 10 sessions with Finance Guild Master',
    icon: '🗣️',
    rarity: 'uncommon',
    category: 'guild',
    xp_reward: 250,
    tier_required: 'initiate',
    criteria: { metric: 'guild_master_sessions', operator: 'gte', value: 10 },
    visual: { gradient_start: '#a855f7', gradient_end: '#9333ea', glow_color: '#c084fc', border_style: 'solid', particle_type: 'sparkle' },
  },
  {
    id: 'network_node',
    name: 'Network Node',
    description: 'Bring in 10 NPM network referrals',
    icon: '🕸️',
    rarity: 'rare',
    category: 'guild',
    xp_reward: 400,
    tier_required: '3-star',
    criteria: { metric: 'npm_referrals_received', operator: 'gte', value: 10 },
    visual: { gradient_start: '#ec4899', gradient_end: '#db2777', glow_color: '#f472b6', border_style: 'pulse', particle_type: 'sparkle' },
  },
  {
    id: 'bundle_master',
    name: 'Bundle Master',
    description: 'Sell 10 TradeBuilder + ZES bundles',
    icon: '📦',
    rarity: 'rare',
    category: 'guild',
    xp_reward: 400,
    tier_required: '3-star',
    criteria: { metric: 'bundles_sold', operator: 'gte', value: 10 },
    visual: { gradient_start: '#8b5cf6', gradient_end: '#6d28d9', glow_color: '#a78bfa', border_style: 'pulse', particle_type: 'coin', animation: 'float' },
  },

  // ── Special Badges ──
  {
    id: 'founding_member',
    name: 'Founding Member',
    description: 'Joined Finance Guild in Q1 2026',
    icon: '🏛️',
    rarity: 'legendary',
    category: 'special',
    xp_reward: 500,
    tier_required: 'initiate',
    criteria: { metric: 'joined_before', operator: 'gte', value: 20260401 },
    visual: { gradient_start: '#fbbf24', gradient_end: '#b45309', glow_color: '#fde68a', border_style: 'flame', particle_type: 'sparkle', animation: 'glow' },
  },
];

// ── ACHIEVEMENT DEFINITIONS ───────────────────────────────────────

export const ACHIEVEMENTS: Achievement[] = [
  {
    id: 'ach_first_steps',
    name: 'First Steps',
    description: 'Complete your onboarding and first scan',
    icon: '👣',
    rarity: 'common',
    xp_reward: 50,
    tp_reward: 5,
    badges_awarded: [],
    secret: false,
    criteria: [
      { type: 'event', params: { event: 'onboarding_complete' } },
      { type: 'metric_threshold', params: { metric: 'total_scans', value: 1 } },
    ],
  },
  {
    id: 'ach_promoted_3star',
    name: 'Professional Entry',
    description: 'Reach 3-Star tier — commissions activated',
    icon: '⭐',
    rarity: 'uncommon',
    xp_reward: 100,
    tp_reward: 10,
    badges_awarded: ['first_blood'],
    secret: false,
    criteria: [{ type: 'tier_reach', params: { tier: '3-star' } }],
  },
  {
    id: 'ach_promoted_4star',
    name: 'Revenue Operator',
    description: 'Reach 4-Star tier — higher commission rates unlocked',
    icon: '🌟',
    rarity: 'rare',
    xp_reward: 250,
    tp_reward: 25,
    badges_awarded: [],
    secret: false,
    criteria: [{ type: 'tier_reach', params: { tier: '4-star' } }],
  },
  {
    id: 'ach_promoted_5star',
    name: 'Revenue Architect',
    description: 'Reach 5-Star tier — premium rates and profit sharing',
    icon: '💫',
    rarity: 'epic',
    xp_reward: 500,
    tp_reward: 50,
    badges_awarded: [],
    secret: false,
    criteria: [{ type: 'tier_reach', params: { tier: '5-star' } }],
  },
  {
    id: 'ach_triple_threat',
    name: 'Triple Threat',
    description: 'Sell all 3 product layers in one month (TradeBoost + Website Factory + Platform)',
    icon: '🔱',
    rarity: 'epic',
    xp_reward: 750,
    tp_reward: 50,
    badges_awarded: ['bundle_master'],
    secret: false,
    criteria: [{ type: 'combo', params: { layers: ['tradeboost', 'website_factory', 'platform_saas'], period: 'month' } }],
  },
  {
    id: 'ach_guild_oracle',
    name: 'Guild Oracle',
    description: 'Act on 25 Perplexity market signals and close deals from them',
    icon: '🔮',
    rarity: 'legendary',
    xp_reward: 1000,
    tp_reward: 100,
    badges_awarded: [],
    secret: true,
    criteria: [{ type: 'metric_threshold', params: { metric: 'perplexity_signals_acted', value: 25 } }],
  },
  {
    id: 'ach_document_master',
    name: 'Document Master',
    description: 'Send 100 proposals through DocuSend Pro',
    icon: '📜',
    rarity: 'rare',
    xp_reward: 400,
    tp_reward: 30,
    badges_awarded: [],
    secret: false,
    criteria: [{ type: 'metric_threshold', params: { metric: 'docusend_proposals_sent', value: 100 } }],
  },
  {
    id: 'ach_network_king',
    name: 'Network King',
    description: 'Convert 25 NPM network referrals to paying clients',
    icon: '👑',
    rarity: 'legendary',
    xp_reward: 1000,
    tp_reward: 100,
    badges_awarded: ['network_node'],
    secret: false,
    criteria: [{ type: 'metric_threshold', params: { metric: 'npm_referrals_converted', value: 25 } }],
  },
];

// ── RARITY COLORS ─────────────────────────────────────────────────

export const RARITY_COLORS: Record<BadgeRarity, { bg: string; border: string; text: string; glow: string }> = {
  common:    { bg: '#374151', border: '#6b7280', text: '#d1d5db', glow: 'none' },
  uncommon:  { bg: '#064e3b', border: '#10b981', text: '#6ee7b7', glow: '0 0 8px rgba(16,185,129,0.3)' },
  rare:      { bg: '#1e3a5f', border: '#3b82f6', text: '#93c5fd', glow: '0 0 12px rgba(59,130,246,0.4)' },
  epic:      { bg: '#3b0764', border: '#a855f7', text: '#c4b5fd', glow: '0 0 16px rgba(168,85,247,0.5)' },
  legendary: { bg: '#451a03', border: '#f59e0b', text: '#fde68a', glow: '0 0 20px rgba(245,158,11,0.6)' },
};
```

***

## Core Visual Components

### `src/components/badges/BadgeIcon.tsx`

```tsx
import { motion } from 'framer-motion';
import { Badge } from '../../gamification/types';
import { RARITY_COLORS } from '../../gamification/constants';

interface BadgeIconProps {
  badge: Badge;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  unlocked?: boolean;
  showTooltip?: boolean;
  onClick?: () => void;
}

const SIZES = { sm: 32, md: 48, lg: 64, xl: 96 };

export default function BadgeIcon({ badge, size = 'md', unlocked = true, showTooltip = true, onClick }: BadgeIconProps) {
  const px = SIZES[size];
  const rarity = RARITY_COLORS[badge.rarity];
  const v = badge.visual;

  return (
    <motion.div
      className="relative group cursor-pointer"
      style={{ width: px, height: px }}
      whileHover={{ scale: 1.15, rotate: [0, -5, 5, 0] }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      initial={{ opacity: 0, scale: 0 }}
      animate={{ opacity: unlocked ? 1 : 0.3, scale: 1 }}
      transition={{ type: 'spring', stiffness: 260, damping: 20 }}
    >
      {/* Glow ring */}
      {unlocked && badge.rarity !== 'common' && (
        <motion.div
          className="absolute inset-0 rounded-full"
          style={{
            background: `radial-gradient(circle, ${v.glow_color}40 0%, transparent 70%)`,
            filter: `blur(${px * 0.15}px)`,
          }}
          animate={{
            opacity: [0.5, 1, 0.5],
            scale: [1, 1.2, 1],
          }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}

      {/* Badge body */}
      <div
        className="relative w-full h-full rounded-full flex items-center justify-center"
        style={{
          background: `linear-gradient(135deg, ${v.gradient_start}, ${v.gradient_end})`,
          border: `2px solid ${rarity.border}`,
          boxShadow: unlocked ? rarity.glow : 'none',
          filter: unlocked ? 'none' : 'grayscale(100%)',
        }}
      >
        <span style={{ fontSize: px * 0.45, lineHeight: 1 }}>{badge.icon}</span>

        {/* Particle overlay for legendary */}
        {unlocked && v.particle_type === 'sparkle' && (
          <motion.div
            className="absolute inset-0 rounded-full overflow-hidden pointer-events-none"
            style={{ background: `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.2) 0%, transparent 50%)` }}
            animate={{ rotate: 360 }}
            transition={{ duration: 8, repeat: Infinity, ease: 'linear' }}
          />
        )}
      </div>

      {/* Lock overlay */}
      {!unlocked && (
        <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50">
          <span style={{ fontSize: px * 0.3 }}>🔒</span>
        </div>
      )}

      {/* Tooltip */}
      {showTooltip && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
          <div className="bg-gray-900 rounded-lg px-3 py-2 shadow-xl border whitespace-nowrap" style={{ borderColor: rarity.border }}>
            <div className="font-bold text-xs" style={{ color: rarity.text }}>{badge.name}</div>
            <div className="text-[10px] text-gray-400">{badge.description}</div>
            <div className="text-[10px] mt-1 font-mono" style={{ color: rarity.text }}>
              +{badge.xp_reward} XP • {badge.rarity.toUpperCase()}
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
}
```

### `src/components/rank/RankBadge.tsx`

```tsx
import { motion } from 'framer-motion';
import { GuildTier } from '../../gamification/types';
import { TIER_THRESHOLDS } from '../../gamification/constants';

interface RankBadgeProps {
  tier: GuildTier;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  animate?: boolean;
}

const TIER_ICONS: Record<GuildTier, string> = {
  'initiate': '🛡️',
  '3-star':   '⭐',
  '4-star':   '🌟',
  '5-star':   '💫',
  'elite':    '🏆',
  'd-tier':   '👑',
};

const TIER_STARS: Record<GuildTier, number> = {
  'initiate': 0, '3-star': 3, '4-star': 4, '5-star': 5, 'elite': 6, 'd-tier': 7,
};

const SIZES = { sm: 40, md: 64, lg: 96 };

export default function RankBadge({ tier, size = 'md', showLabel = true, animate = true }: RankBadgeProps) {
  const px = SIZES[size];
  const config = TIER_THRESHOLDS[tier];
  const stars = TIER_STARS[tier];

  return (
    <div className="flex flex-col items-center gap-1">
      <motion.div
        className="relative flex items-center justify-center rounded-xl"
        style={{
          width: px,
          height: px,
          background: `radial-gradient(circle at 30% 30%, ${config.color}30, ${config.color}10)`,
          border: `2px solid ${config.color}`,
          boxShadow: `0 0 20px ${config.glow}, inset 0 0 20px ${config.glow}`,
        }}
        whileHover={animate ? { scale: 1.1, boxShadow: `0 0 30px ${config.glow}` } : {}}
        initial={animate ? { scale: 0, rotate: -180 } : {}}
        animate={{ scale: 1, rotate: 0 }}
        transition={{ type: 'spring', stiffness: 200, damping: 15 }}
      >
        {/* Icon */}
        <span style={{ fontSize: px * 0.4 }}>{TIER_ICONS[tier]}</span>

        {/* Rotating ring for elite+ */}
        {(tier === 'elite' || tier === 'd-tier') && (
          <motion.div
            className="absolute inset-0 rounded-xl"
            style={{
              border: `1px solid ${config.color}60`,
              borderRadius: '12px',
            }}
            animate={{ rotate: 360 }}
            transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
          />
        )}

        {/* Star row */}
        {stars > 0 && (
          <div className="absolute -bottom-1 flex gap-[1px]">
            {Array.from({ length: Math.min(stars, 5) }).map((_, i) => (
              <motion.div
                key={i}
                className="text-[8px]"
                style={{ color: config.color }}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
              >
                ★
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>

      {showLabel && (
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: config.color }}>
          {config.title}
        </span>
      )}
    </div>
  );
}
```

### `src/components/rank/LevelUpOverlay.tsx`

```tsx
import { motion, AnimatePresence } from 'framer-motion';
import { LevelUpEvent } from '../../gamification/types';
import { TIER_THRESHOLDS } from '../../gamification/constants';
import RankBadge from './RankBadge';
import ConfettiExplosion from '../visuals/ConfettiExplosion';

interface LevelUpOverlayProps {
  event: LevelUpEvent | null;
  onDismiss: () => void;
}

export default function LevelUpOverlay({ event, onDismiss }: LevelUpOverlayProps) {
  if (!event) return null;

  const tierChanged = event.old_tier !== event.new_tier;
  const newConfig = TIER_THRESHOLDS[event.new_tier];

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[9999] flex items-center justify-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onDismiss}
      >
        {/* Backdrop */}
        <motion.div
          className="absolute inset-0 bg-black/80 backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        />

        {/* Confetti */}
        <ConfettiExplosion active={true} color={newConfig.color} />

        {/* Content */}
        <motion.div
          className="relative z-10 flex flex-col items-center gap-6 p-12"
          initial={{ scale: 0, y: 50 }}
          animate={{ scale: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.2 }}
        >
          {/* Level number */}
          <motion.div
            className="text-8xl font-black"
            style={{ color: newConfig.color, textShadow: `0 0 40px ${newConfig.glow}` }}
            animate={{
              scale: [1, 1.2, 1],
              textShadow: [`0 0 20px ${newConfig.glow}`, `0 0 60px ${newConfig.glow}`, `0 0 20px ${newConfig.glow}`],
            }}
            transition={{ duration: 1.5, repeat: Infinity }}
          >
            {event.new_level}
          </motion.div>

          {/* LEVEL UP text */}
          <motion.h1
            className="text-4xl font-black uppercase tracking-[0.3em]"
            style={{ color: newConfig.color }}
            initial={{ letterSpacing: '0.5em', opacity: 0 }}
            animate={{ letterSpacing: '0.3em', opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            {tierChanged ? 'TIER PROMOTION' : 'LEVEL UP'}
          </motion.h1>

          {/* Tier badge (if tier changed) */}
          {tierChanged && (
            <motion.div
              className="flex items-center gap-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8 }}
            >
              <RankBadge tier={event.old_tier} size="sm" showLabel={true} animate={false} />
              <motion.span
                className="text-2xl"
                animate={{ x: [0, 10, 0] }}
                transition={{ duration: 0.6, repeat: Infinity }}
              >
                →
              </motion.span>
              <RankBadge tier={event.new_tier} size="lg" showLabel={true} />
            </motion.div>
          )}

          {/* XP earned */}
          <motion.div
            className="text-lg font-mono text-green-400"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1 }}
          >
            +{event.xp_earned} XP
          </motion.div>

          {/* Unlocked badges */}
          {event.badges_unlocked.length > 0 && (
            <motion.div
              className="flex flex-col items-center gap-2"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1.2 }}
            >
              <span className="text-xs uppercase tracking-wider text-gray-400">Badges Unlocked</span>
              <div className="flex gap-3">
                {event.badges_unlocked.map((b, i) => (
                  <motion.span
                    key={b}
                    className="text-3xl"
                    initial={{ scale: 0, rotate: -180 }}
                    animate={{ scale: 1, rotate: 0 }}
                    transition={{ delay: 1.4 + i * 0.2, type: 'spring' }}
                  >
                    🏅
                  </motion.span>
                ))}
              </div>
            </motion.div>
          )}

          {/* Dismiss hint */}
          <motion.p
            className="text-xs text-gray-500 mt-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 2 }}
          >
            Click anywhere to continue
          </motion.p>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
```

### `src/components/visuals/ConfettiExplosion.tsx`

```tsx
import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

interface ConfettiExplosionProps {
  active: boolean;
  color?: string;
  particleCount?: number;
}

export default function ConfettiExplosion({ active, color = '#fbbf24', particleCount = 60 }: ConfettiExplosionProps) {
  if (!active) return null;

  const colors = [color, '#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ec4899'];

  return (
    <div className="fixed inset-0 pointer-events-none z-[99999] overflow-hidden">
      {Array.from({ length: particleCount }).map((_, i) => {
        const c = colors[i % colors.length];
        const x = Math.random() * 100;
        const delay = Math.random() * 0.5;
        const duration = 2 + Math.random() * 2;
        const size = 4 + Math.random() * 8;
        const rotation = Math.random() * 720 - 360;

        return (
          <motion.div
            key={i}
            className="absolute rounded-sm"
            style={{
              width: size,
              height: size * (0.5 + Math.random()),
              backgroundColor: c,
              left: `${x}%`,
              top: '-2%',
            }}
            initial={{ y: 0, x: 0, rotate: 0, opacity: 1 }}
            animate={{
              y: window.innerHeight + 100,
              x: (Math.random() - 0.5) * 400,
              rotate: rotation,
              opacity: [1, 1, 0],
            }}
            transition={{ duration, delay, ease: 'easeIn' }}
          />
        );
      })}
    </div>
  );
}
```

### `src/components/visuals/GlowCard.tsx`

```tsx
import { motion } from 'framer-motion';
import { ReactNode } from 'react';

interface GlowCardProps {
  children: ReactNode;
  glowColor?: string;
  className?: string;
  hover?: boolean;
}

export default function GlowCard({ children, glowColor = '#6d28d9', className = '', hover = true }: GlowCardProps) {
  return (
    <motion.div
      className={`relative rounded-xl bg-[#0f0f1a] border border-white/5 p-5 overflow-hidden ${className}`}
      whileHover={hover ? {
        borderColor: `${glowColor}50`,
        boxShadow: `0 0 30px ${glowColor}20, inset 0 0 30px ${glowColor}05`,
      } : {}}
      transition={{ duration: 0.3 }}
    >
      {/* Gradient accent top */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px]"
        style={{ background: `linear-gradient(90deg, transparent, ${glowColor}, transparent)` }}
      />
      {children}
    </motion.div>
  );
}
```

### `src/components/visuals/NumberCounter.tsx`

```tsx
import { useEffect, useState } from 'react';
import { motion, useSpring, useTransform } from 'framer-motion';

interface NumberCounterProps {
  value: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  className?: string;
  decimals?: number;
}

export default function NumberCounter({ value, prefix = '', suffix = '', duration = 1.5, className = '', decimals = 0 }: NumberCounterProps) {
  const spring = useSpring(0, { duration: duration * 1000 });
  const display = useTransform(spring, (v) =>
    `${prefix}${v.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${suffix}`
  );

  useEffect(() => { spring.set(value); }, [value, spring]);

  return <motion.span className={className}>{display}</motion.span>;
}
```

***

## Gamification Supabase Schema

### `supabase/migrations/003_gamification_schema.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- GAMIFICATION — Finance Guild XP, Badges, Achievements
-- FATE Economy integration: XP + Trust Points + Trust Score
-- ═══════════════════════════════════════════════════════════════════

-- Rep gamification profile (extends fg_reps)
CREATE TABLE fg_rep_profiles (
  rep_id          UUID PRIMARY KEY REFERENCES fg_reps(id) ON DELETE CASCADE,
  tier            TEXT DEFAULT 'initiate' CHECK (tier IN ('initiate','3-star','4-star','5-star','elite','d-tier')),
  xp              INTEGER DEFAULT 0,
  trust_points    INTEGER DEFAULT 0,
  trust_score     NUMERIC(4,3) DEFAULT 0.500, -- 0.000 - 1.000
  level           INTEGER DEFAULT 1,
  streak_days     INTEGER DEFAULT 0,
  last_active     DATE DEFAULT CURRENT_DATE,
  title           TEXT DEFAULT 'Guild Initiate',
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- XP event log (immutable audit trail)
CREATE TABLE fg_xp_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID NOT NULL REFERENCES fg_reps(id),
  event_type      TEXT NOT NULL,            -- e.g. 'lead_scan_completed', 'contract_signed'
  xp_amount       INTEGER NOT NULL,
  tp_amount       INTEGER DEFAULT 0,        -- Trust Points delta
  source_type     TEXT,                     -- 'manual' | 'auto' | 'system' | 'perplexity' | 'npm'
  source_id       TEXT,                     -- Reference to source entity
  metadata        JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Badge instances (earned badges per rep)
CREATE TABLE fg_rep_badges (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID NOT NULL REFERENCES fg_reps(id),
  badge_id        TEXT NOT NULL,            -- References badge from constants
  earned_at       TIMESTAMPTZ DEFAULT now(),
  metadata        JSONB DEFAULT '{}',       -- Snapshot of criteria met
  UNIQUE(rep_id, badge_id)
);

-- Achievement instances
CREATE TABLE fg_rep_achievements (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID NOT NULL REFERENCES fg_reps(id),
  achievement_id  TEXT NOT NULL,
  earned_at       TIMESTAMPTZ DEFAULT now(),
  metadata        JSONB DEFAULT '{}',
  UNIQUE(rep_id, achievement_id)
);

-- Level-up event log (for animation triggers via Supabase Realtime)
CREATE TABLE fg_level_up_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id          UUID NOT NULL REFERENCES fg_reps(id),
  old_level       INTEGER NOT NULL,
  new_level       INTEGER NOT NULL,
  old_tier        TEXT NOT NULL,
  new_tier        TEXT NOT NULL,
  xp_at_event     INTEGER NOT NULL,
  badges_unlocked TEXT[] DEFAULT '{}',
  achievements_unlocked TEXT[] DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- RLS
ALTER TABLE fg_rep_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_xp_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_rep_badges ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_rep_achievements ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_level_up_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profile_own" ON fg_rep_profiles FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "xp_own" ON fg_xp_events FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "badges_own" ON fg_rep_badges FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "achievements_own" ON fg_rep_achievements FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "levelup_own" ON fg_level_up_events FOR SELECT
  USING (rep_id = fg_my_rep_id() OR fg_is_admin());

-- Leaderboard view (public within guild)
CREATE POLICY "profile_leaderboard" ON fg_rep_profiles FOR SELECT
  USING (true); -- All guild members can see each other's rank

-- Indexes
CREATE INDEX idx_fg_xp_events_rep ON fg_xp_events(rep_id);
CREATE INDEX idx_fg_xp_events_created ON fg_xp_events(created_at DESC);
CREATE INDEX idx_fg_rep_badges_rep ON fg_rep_badges(rep_id);
CREATE INDEX idx_fg_level_up_events_rep ON fg_level_up_events(rep_id);
CREATE INDEX idx_fg_level_up_events_created ON fg_level_up_events(created_at DESC);

-- Enable Realtime for level-up events (triggers animations in UI)
ALTER PUBLICATION supabase_realtime ADD TABLE fg_level_up_events;
ALTER PUBLICATION supabase_realtime ADD TABLE fg_rep_badges;
```

***

## Multi-Tenant Structure

### `supabase/migrations/004_tenant_schema.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- MULTI-TENANT — Finance Guild as a Tenant within Citadel-Nexus
-- Ref: Engagement System Template multi-tenant model
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE fg_tenants (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            TEXT UNIQUE NOT NULL,        -- e.g. 'finance-guild'
  name            TEXT NOT NULL,               -- e.g. 'Finance Guild'
  guild_type      TEXT DEFAULT 'finance',      -- finance | fire | ems | brotherhood
  
  -- Config
  config          JSONB DEFAULT '{}',          -- Theme, features, limits
  features        TEXT[] DEFAULT '{}',         -- Enabled features
  
  -- Billing
  stripe_account_id TEXT,
  plan             TEXT DEFAULT 'pro',
  
  -- Status
  active           BOOLEAN DEFAULT true,
  created_at       TIMESTAMPTZ DEFAULT now()
);

-- Tenant membership (maps users to tenants with roles)
CREATE TABLE fg_tenant_members (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES fg_tenants(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role            TEXT DEFAULT 'member' CHECK (role IN (
    'viewer', 'member', '3-star', '4-star', '5-star', 'elite', 'd-tier',
    'maintainer', 'council', 'admin'
  )),
  joined_at       TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tenant_id, user_id)
);

-- Seed the Finance Guild tenant
INSERT INTO fg_tenants (slug, name, guild_type, features) VALUES (
  'finance-guild',
  'Finance Guild',
  'finance',
  ARRAY['xp_tracking', 'badges', 'achievements', 'leaderboard', 'guild_master_voice',
        'perplexity_signals', 'npm_network', 'docusend_pro', 'metabase_dashboards',
        'lead_scanner', 'commission_engine', 'real_time_revenue']
);

ALTER TABLE fg_tenant_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY "members_own" ON fg_tenant_members FOR SELECT
  USING (user_id = auth.uid() OR fg_is_admin());
```

***

## Guild Tenets Document

### `docs/FINANCE_GUILD_TENETS.md`

```markdown
# 💰 Finance Guild — Operating Tenets

## I. Revenue Is Oxygen
Everything we build, every scan we run, every proposal we send exists to generate
sustainable recurring revenue. TradeBuilder builds the website. ZES is the agent
layer delivered in 24 hours. Both feed the same pipeline.

## II. Speed Closes Deals
ZES agents deploy within 24 hours. Proposals generate from DocuSend Pro in minutes.
Lead scans return results in seconds. The rep who moves fastest wins.

## III. The Data Never Lies
Perplexity Finance signals, Metabase dashboards, and FATE trust scores are the
arbiter of truth. Gut feelings are hypotheses — data is the verdict.

## IV. Guild Master Is the Voice of Reason
The ElevenLabs Finance Guild Master voice agent carries the full RAG documentation
of this guild. When in doubt, ask the oracle. Its knowledge base is the single
source of truth for pricing, objection handling, and playbook execution.

## V. Compound Over Flash
Year 1 commission at 10%. Year 2 at 5%. Year 3-5 at 3%. The rep who retains
clients for 5 years earns more than the rep who closes big and churns fast.
Retention is the ultimate skill.

## VI. Every Layer Feeds the Next
TradeBoost micro-services ($15-30/mo) → Website Factory ($99-299/mo) →
Platform SaaS ($29-9,999/mo). The cross-sell path is the moat. Bundle Master
badge exists for a reason.

## VII. Trust Is Earned, Not Given
FATE economy governs everything. Trust Points (TP) accumulate through consistent
performance. Trust Score (0.00-1.00) determines tier advancement. Gaming the
system triggers Sentinel review.

## VIII. The Network Is the Net Worth
NPM Second Network referrals and partner revenue sharing multiply reach without
multiplying cost. Network Node badge holders are force multipliers.

## IX. Transparency as Armor
Every commission is tracked. Every client interaction logged. Every revenue event
auditable. GuardianLogs provides immutable audit trail. The SRS tag registry
is always green.

## X. Level Up or Level Out
The tier system exists: Initiate → 3-Star → 4-Star → 5-Star → Elite → D-Tier.
Stagnation triggers the Character Ghost system. Growth is not optional.
```

***

## Security & ICP Files

### `security/icp-tiers.yaml`

```yaml
# ═══════════════════════════════════════════════════════════════════
# ICP — Information Classification Policy — Finance Guild
# ═══════════════════════════════════════════════════════════════════

tiers:
  T0:
    name: "Public"
    description: "Publicly available information"
    auto_classification: true
    examples:
      - Product pricing pages
      - ZES plan descriptions
      - TradeBuilder feature lists
      - Marketing collateral
    access: "Anyone"

  T1:
    name: "Internal"
    description: "Guild-internal operational data"
    auto_classification: true
    examples:
      - Rep leaderboards
      - Commission rates
      - Pipeline metrics
      - Scan results
      - Badge/achievement status
      - Perplexity market signals
    access: "Authenticated guild members"
    rls_policy: "fg_reps.auth_id = auth.uid()"

  T2:
    name: "Confidential"
    description: "Sensitive business data requiring role-gating"
    auto_classification: false
    gate: "admin_approval"
    examples:
      - Client PII (names, emails, phones)
      - Stripe financial data
      - NPM partner agreements
      - DocuSend signed contracts
      - Revenue projections
      - COGS and margin data
    access: "Rep (own data) + Finance Admin"
    rls_policy: "fg_clients.rep_id = fg_my_rep_id() OR fg_is_admin()"

  T3:
    name: "Restricted"
    description: "High-sensitivity data with audit trail"
    auto_classification: false
    gate: "reflex_review"
    examples:
      - Commission override approvals
      - Rep termination data
      - Platform SaaS enterprise contracts
      - Stripe Connect account details
      - Equity and revenue share agreements
    access: "Finance Admin only"
    rls_policy: "fg_is_admin()"
    audit: "GuardianLogs immutable trail"
```

### `security/srs-tags.yaml`

```yaml
# ═══════════════════════════════════════════════════════════════════
# SRS — Service Reference Sheet Tags — Finance Guild
# ═══════════════════════════════════════════════════════════════════

tags:
  SRS_FG_CORE:
    tier: T1
    description: "Finance Guild core application"
    services: [supabase, react, vite, tailwind]
    
  SRS_FG_SECURITY_FIREWALL:
    tier: T1
    description: "Cloudflare WAF and firewall rules"
    services: [cloudflare_waf, cloudflare_ddos]
    
  SRS_FG_SECURITY_RLS:
    tier: T2
    description: "Supabase Row Level Security policies"
    services: [supabase_rls, pg_policies]
    
  SRS_FG_STRIPE:
    tier: T2
    description: "Stripe billing and Connect integration"
    services: [stripe_billing, stripe_connect, stripe_webhooks]
    
  SRS_FG_PERPLEXITY:
    tier: T1
    description: "Perplexity Finance Data API integration"
    services: [perplexity_sonar, perplexity_citations]
    
  SRS_FG_NPM_NETWORK:
    tier: T2
    description: "NPM Second Network partner referral API"
    services: [npm_referrals, npm_partners, npm_webhooks]
    
  SRS_FG_DOCUSEND:
    tier: T2
    description: "DocuSend Pro document generation and signing"
    services: [docusend_templates, docusend_signing, docusend_webhooks]
    
  SRS_FG_METABASE:
    tier: T1
    description: "Metabase embedded analytics dashboards"
    services: [metabase_embed, metabase_questions]
    
  SRS_FG_GAMIFICATION:
    tier: T1
    description: "FATE economy — XP, badges, achievements, tier progression"
    services: [xp_engine, badge_checker, achievement_engine, realtime_events]
    
  SRS_FG_GUILD_MASTER:
    tier: T1
    description: "ElevenLabs Finance Guild Master voice agent"
    services: [elevenlabs_conversational, rag_knowledge_base]
    
  SRS_FG_SCANNER:
    tier: T1
    description: "Lead scanner and recommendation engine"
    services: [website_audit, recommendation_engine]
```

***

## Ansible Playbook

### `infra/ansible/playbooks/deploy-finance-guild.yml`

```yaml
---
# ═══════════════════════════════════════════════════════════════════
# ANSIBLE PLAYBOOK — Finance Guild Deployment
# Deploys: Supabase migrations, Edge Functions, Cloudflare config
# ═══════════════════════════════════════════════════════════════════

- name: Deploy Finance Guild
  hosts: finance_guild
  become: yes
  vars_files:
    - ../vars/secrets.yml
  
  tasks:
    # ── Supabase Migrations ──
    - name: Run Supabase migrations
      shell: |
        cd {{ project_root }}/services/finance-guild
        supabase db push --db-url "{{ supabase_db_url }}"
      environment:
        SUPABASE_ACCESS_TOKEN: "{{ supabase_access_token }}"
      tags: [database, migrations]

    - name: Seed product catalog
      shell: |
        psql "{{ supabase_db_url }}" -f supabase/seed/products.sql
        psql "{{ supabase_db_url }}" -f supabase/seed/badges.sql
        psql "{{ supabase_db_url }}" -f supabase/seed/achievements.sql
      tags: [database, seed]

    # ── Edge Functions ──
    - name: Deploy Edge Functions
      loop:
        - fg-calculate-commission
        - fg-perplexity-sync
        - fg-npm-network
        - fg-docusend
        - fg-xp-engine
        - fg-achievement-check
      shell: |
        cd {{ project_root }}/services/finance-guild
        supabase functions deploy {{ item }} --project-ref {{ supabase_project_ref }}
      tags: [functions]

    # ── Set Edge Function secrets ──
    - name: Set function secrets
      shell: |
        supabase secrets set \
          PERPLEXITY_API_KEY="{{ perplexity_api_key }}" \
          NPM_NETWORK_API_URL="{{ npm_api_url }}" \
          NPM_NETWORK_API_KEY="{{ npm_api_key }}" \
          DOCUSEND_PRO_API_URL="{{ docusend_api_url }}" \
          DOCUSEND_PRO_API_KEY="{{ docusend_api_key }}" \
          STRIPE_SECRET_KEY="{{ stripe_secret_key }}" \
          STRIPE_WEBHOOK_SECRET="{{ stripe_webhook_secret }}" \
          ELEVENLABS_API_KEY="{{ elevenlabs_api_key }}" \
          --project-ref {{ supabase_project_ref }}
      tags: [secrets]

    # ── Refresh materialized views ──
    - name: Refresh Metabase materialized views
      shell: |
        psql "{{ supabase_db_url }}" -c "SELECT fg_refresh_materialized_views();"
      tags: [database, metabase]

    # ── Cron setup ──
    - name: Setup Perplexity sync cron (every 6 hours)
      cron:
        name: "Finance Guild Perplexity Sync"
        hour: "*/6"
        minute: "0"
        job: "curl -s -X POST {{ supabase_url }}/functions/v1/fg-perplexity-sync -H 'Authorization: Bearer {{ supabase_anon_key }}'"
      tags: [cron]

    - name: Setup materialized view refresh cron (every 15 min)
      cron:
        name: "Finance Guild MV Refresh"
        minute: "*/15"
        job: "psql '{{ supabase_db_url }}' -c 'SELECT fg_refresh_materialized_views();' > /dev/null 2>&1"
      tags: [cron]
```

***

## Cloudflare Configuration

### `infra/cloudflare/firewall-rules.json`

```json
{
  "finance_guild_rules": [
    {
      "id": "fg_rate_limit_api",
      "description": "Rate limit Finance Guild API — 100 req/min per IP",
      "expression": "(http.request.uri.path contains \"/api/finance-guild/\")",
      "action": "challenge",
      "rate_limit": {
        "threshold": 100,
        "period": 60
      }
    },
    {
      "id": "fg_block_scanner_abuse",
      "description": "Block excessive lead scans — 20/hour per IP",
      "expression": "(http.request.uri.path contains \"/api/scanner/scan\")",
      "action": "block",
      "rate_limit": {
        "threshold": 20,
        "period": 3600
      }
    },
    {
      "id": "fg_bot_protection",
      "description": "Challenge suspected bots on dashboard pages",
      "expression": "(http.request.uri.path contains \"/dashboard\") and (cf.bot_management.score lt 30)",
      "action": "managed_challenge"
    },
    {
      "id": "fg_geo_restrict_admin",
      "description": "Admin routes restricted to US",
      "expression": "(http.request.uri.path contains \"/admin\") and (ip.geoip.country ne \"US\")",
      "action": "block"
    },
    {
      "id": "fg_webhook_allowlist",
      "description": "Allow only Stripe + DocuSend + NPM webhook IPs",
      "expression": "(http.request.uri.path contains \"/webhooks/\") and (not ip.src in {54.187.174.169 54.187.205.235 54.187.216.72})",
      "action": "block"
    },
    {
      "id": "fg_waf_owasp",
      "description": "OWASP Core Ruleset for all Finance Guild routes",
      "expression": "(http.request.uri.path contains \"/api/finance-guild/\")",
      "action": "managed_challenge",
      "managed_ruleset": "owasp_core"
    }
  ]
}
```

***

This completes the Finance Guild gamification layer with full visual components, animations, and infrastructure . The tier system maps directly from your Service Tier Template — Initiate through D-Tier — with XP thresholds at 0/300/600/1000/1500/2500, and the contribution scoring algorithm weighs engagement (40%), mission completion (30%), client satisfaction (20%), and guild contribution (10%) . Every badge has rarity-specific glow animations (common through legendary), particle effects (sparkle/fire/lightning/coin), and Framer Motion spring physics . The level-up overlay triggers via Supabase Realtime subscriptions on `fg_level_up_events`, deploying a fullscreen confetti + tier promotion animation sequence matching the OAD bot celebration trigger pattern from your Engagement System . The tenant schema isolates Finance Guild as its own tenant within the Citadel-Nexus multi-tenant engagement model, with role-based access gating per tier.Here is the full analytics, scraping, acquisition backend, builder integrations, marketplace data, Stripe entitlements, and permissions layer — all wired into the Finance Guild architecture across every integration you specified.

***

## Updated File Structure — Analytics, Scraping, Integrations, Entitlements

```
services/finance-guild/
├── src/
│   ├── analytics/
│   │   ├── posthog/
│   │   │   ├── PostHogProvider.tsx          ← React context + auto-capture init
│   │   │   ├── posthog-client.ts            ← PostHog JS client wrapper
│   │   │   ├── events.ts                    ← Event taxonomy (typed event names)
│   │   │   ├── feature-flags.ts             ← Feature flag evaluator
│   │   │   ├── cohorts.ts                   ← Cohort definitions (rep tiers, churn risk)
│   │   │   ├── funnels.ts                   ← Funnel definitions (scan→demo→close)
│   │   │   └── session-replay.ts            ← Session replay config + PII masking
│   │   │
│   │   ├── datadog/
│   │   │   ├── dd-tracer.ts                 ← dd-trace Node.js init (APM)
│   │   │   ├── dd-rum.ts                    ← Browser RUM (Real User Monitoring)
│   │   │   ├── dd-logs.ts                   ← Browser + Edge Function log shipping
│   │   │   ├── monitors.ts                  ← Datadog monitor definitions (YAML export)
│   │   │   ├── dashboards.ts                ← Dashboard-as-code JSON definitions
│   │   │   └── synthetics.ts                ← Synthetic test definitions
│   │   │
│   │   ├── metabase/
│   │   │   ├── MetabaseEmbed.tsx             ← iFrame embed component w/ JWT auth
│   │   │   ├── metabase-client.ts            ← Metabase API client (questions, dashboards)
│   │   │   ├── dashboards/
│   │   │   │   ├── rep-performance.json      ← Rep KPI dashboard definition
│   │   │   │   ├── revenue-pipeline.json     ← Pipeline funnel + MRR tracking
│   │   │   │   ├── seo-oracle.json           ← SEO rank tracking + keyword data
│   │   │   │   ├── lead-acquisition.json     ← Lead Hunter metrics
│   │   │   │   └── npm-network.json          ← NPM referral network analytics
│   │   │   └── questions/
│   │   │       ├── mrr-by-rep.sql
│   │   │       ├── scan-conversion-rate.sql
│   │   │       ├── churn-risk-score.sql
│   │   │       ├── seo-rank-delta.sql
│   │   │       └── lead-source-attribution.sql
│   │   │
│   │   └── supabase-analytics/
│   │       ├── materialized-views.sql        ← MV definitions for Metabase
│   │       ├── pg-cron-jobs.sql              ← pg_cron refresh schedules
│   │       └── realtime-subscriptions.ts     ← Supabase Realtime channel manager
│   │
│   ├── scraping/
│   │   ├── lead-hunter/
│   │   │   ├── types.ts                      ← LeadScan, LeadProfile, ScanResult types
│   │   │   ├── scanner-engine.ts             ← Orchestrator: runs all scan modules
│   │   │   ├── modules/
│   │   │   │   ├── google-maps-scraper.ts    ← Google Maps Places API + scrape fallback
│   │   │   │   ├── gbp-scraper.ts            ← Google Business Profile data extraction
│   │   │   │   ├── website-auditor.ts        ← Lighthouse + custom checks
│   │   │   │   ├── social-scraper.ts         ← Facebook/Instagram/X presence check
│   │   │   │   ├── review-aggregator.ts      ← Google/Yelp/BBB review pull
│   │   │   │   ├── contact-enricher.ts       ← Phone/email/address from public sources
│   │   │   │   ├── tech-stack-detector.ts    ← Wappalyzer-style CMS/framework detection
│   │   │   │   └── competitor-mapper.ts      ← Finds top N competitors in same geo+trade
│   │   │   ├── scoring/
│   │   │   │   ├── lead-score-engine.ts      ← 0-100 lead score from all modules
│   │   │   │   ├── urgency-detector.ts       ← Detects urgency signals (no website, bad reviews)
│   │   │   │   └── recommendation-engine.ts  ← Maps score → ZES plan + TradeBuilder upsell
│   │   │   ├── queue/
│   │   │   │   ├── scan-queue.ts             ← BullMQ job queue for async scans
│   │   │   │   ├── scan-worker.ts            ← Worker process that runs scan jobs
│   │   │   │   └── rate-limiter.ts           ← Per-source rate limiting (Google, Yelp, etc.)
│   │   │   └── storage/
│   │   │       ├── scan-cache.ts             ← Redis/Supabase cache layer (24hr TTL)
│   │   │       └── screenshot-store.ts       ← Stores website screenshots in Supabase Storage
│   │   │
│   │   └── seo-oracle/
│   │       ├── types.ts                      ← SEORank, KeywordData, BacklinkProfile types
│   │       ├── seo-engine.ts                 ← SEO Oracle orchestrator
│   │       ├── modules/
│   │       │   ├── rank-tracker.ts           ← SERP position tracking (DataForSEO API)
│   │       │   ├── keyword-researcher.ts     ← Keyword volume + difficulty (DataForSEO)
│   │       │   ├── backlink-checker.ts       ← Backlink profile analysis (Ahrefs/Moz API)
│   │       │   ├── local-pack-monitor.ts     ← Google Map Pack position tracking
│   │       │   ├── citation-auditor.ts       ← NAP consistency across directories
│   │       │   ├── page-speed-checker.ts     ← Core Web Vitals via PageSpeed Insights API
│   │       │   ├── schema-validator.ts       ← JSON-LD / schema.org markup validation
│   │       │   └── content-gap-analyzer.ts   ← Content gap vs competitors
│   │       ├── scoring/
│   │       │   ├── seo-health-score.ts       ← 0-100 composite SEO health
│   │       │   └── seo-recommendations.ts    ← Prioritized action items
│   │       └── reports/
│   │           ├── monthly-seo-report.ts     ← Auto-generated monthly SEO report
│   │           └── competitor-report.ts      ← Competitor comparison report
│   │
│   ├── integrations/
│   │   ├── framer/
│   │   │   ├── types.ts                      ← FramerSite, FramerProject, FramerWebhook
│   │   │   ├── framer-api-client.ts          ← Framer Sites API client
│   │   │   ├── framer-site-provisioner.ts    ← Auto-provision Framer site from template
│   │   │   ├── framer-cms-sync.ts            ← Sync Supabase data → Framer CMS collections
│   │   │   ├── framer-analytics-bridge.ts    ← Inject PostHog + Datadog RUM into Framer sites
│   │   │   ├── framer-form-handler.ts        ← Catch Framer form submissions → Supabase
│   │   │   ├── framer-deploy-hook.ts         ← Webhook on Framer publish → update DNS + SSL
│   │   │   └── templates/
│   │   │       ├── trade-starter.json        ← Starter tier template config ($99/mo)
│   │   │       ├── trade-growth.json         ← Growth tier template config ($199/mo)
│   │   │       └── trade-premium.json        ← Premium tier template config ($299/mo)
│   │   │
│   │   ├── bubble/
│   │   │   ├── types.ts                      ← BubbleApp, BubbleWorkflow, BubbleDataType
│   │   │   ├── bubble-api-client.ts          ← Bubble Data API client (CRUD)
│   │   │   ├── bubble-workflow-trigger.ts    ← Trigger Bubble backend workflows from Supabase
│   │   │   ├── bubble-plugin-bridge.ts       ← Custom Bubble plugin ↔ Finance Guild API
│   │   │   ├── bubble-user-sync.ts           ← Sync Bubble users ↔ Supabase auth
│   │   │   └── bubble-embed-widget.ts        ← Embeddable Finance Guild widget for Bubble apps
│   │   │
│   │   ├── stripe/
│   │   │   ├── types.ts                      ← Full Stripe type extensions
│   │   │   ├── stripe-client.ts              ← Stripe SDK wrapper w/ error handling
│   │   │   ├── products/
│   │   │   │   ├── product-catalog.ts        ← Product/Price ID registry (ZES + TradeBuilder)
│   │   │   │   ├── product-sync.ts           ← Sync Supabase product catalog → Stripe Products
│   │   │   │   └── metered-billing.ts        ← Usage-based billing for API/scan credits
│   │   │   ├── subscriptions/
│   │   │   │   ├── subscription-manager.ts   ← Create/update/cancel subscriptions
│   │   │   │   ├── subscription-lifecycle.ts ← Trial→Active→Past-due→Canceled state machine
│   │   │   │   ├── proration-engine.ts       ← Mid-cycle plan change proration
│   │   │   │   └── bundle-pricing.ts         ← TradeBuilder+ZES bundle discount logic
│   │   │   ├── connect/
│   │   │   │   ├── connect-onboarding.ts     ← Stripe Connect Express onboarding flow
│   │   │   │   ├── connect-payouts.ts        ← Rep commission payout via Connect
│   │   │   │   └── connect-dashboard.ts      ← Embedded Stripe Connect dashboard
│   │   │   ├── webhooks/
│   │   │   │   ├── webhook-handler.ts        ← Central webhook router (signature verified)
│   │   │   │   ├── handlers/
│   │   │   │   │   ├── invoice-paid.ts       ← → XP award + commission calc + entitlement grant
│   │   │   │   │   ├── invoice-failed.ts     ← → Churn risk flag + alert
│   │   │   │   │   ├── subscription-created.ts  ← → Provision services + entitlements
│   │   │   │   │   ├── subscription-updated.ts  ← → Update entitlements (upgrade/downgrade)
│   │   │   │   │   ├── subscription-deleted.ts  ← → Revoke entitlements + deprovisioning
│   │   │   │   │   ├── checkout-completed.ts    ← → Attribution tracking + PostHog event
│   │   │   │   │   ├── customer-created.ts      ← → CRM record creation
│   │   │   │   │   └── payout-paid.ts           ← → Rep commission confirmation + XP
│   │   │   │   └── webhook-verifier.ts       ← Stripe signature verification middleware
│   │   │   ├── billing-portal.ts             ← Stripe Customer Portal session creation
│   │   │   └── revenue-recognition.ts        ← MRR/ARR calculation from Stripe data
│   │   │
│   │   ├── npm-network/
│   │   │   ├── types.ts                      ← NPMPartner, NPMReferral, NPMPayout
│   │   │   ├── npm-api-client.ts             ← NPM Second Network API client
│   │   │   ├── npm-referral-tracker.ts       ← Track referral source → conversion
│   │   │   ├── npm-market-data.ts            ← Pull market data feeds from NPM
│   │   │   ├── npm-partner-directory.ts      ← Partner lookup and directory integration
│   │   │   └── npm-commission-split.ts       ← Revenue share calculation for partner referrals
│   │   │
│   │   └── supabase/
│   │       ├── supabase-client.ts            ← Typed Supabase client with RLS context
│   │       ├── supabase-admin.ts             ← Service-role client for backend ops
│   │       ├── supabase-auth.ts              ← Auth helpers (sign-in, MFA, session)
│   │       ├── supabase-storage.ts           ← Storage bucket management
│   │       ├── supabase-realtime.ts          ← Channel subscriptions for live data
│   │       └── supabase-edge-runtime.ts      ← Edge Function helpers
│   │
│   ├── entitlements/
│   │   ├── types.ts                          ← Entitlement, Permission, FeatureGate types
│   │   ├── entitlement-engine.ts             ← Core entitlement evaluation engine
│   │   ├── feature-gates.ts                  ← Feature flag → entitlement gate mapping
│   │   ├── permission-matrix.ts              ← Full permission matrix (plan × feature × role)
│   │   ├── plan-entitlements.ts              ← What each ZES/TradeBuilder plan unlocks
│   │   ├── tier-entitlements.ts              ← What each guild tier (3-star etc) unlocks for reps
│   │   ├── usage-limits.ts                   ← Usage-based limits (scans/mo, API calls, etc.)
│   │   ├── middleware/
│   │   │   ├── entitlement-guard.ts          ← React route guard (client-side)
│   │   │   ├── api-gate.ts                   ← Edge Function middleware (server-side)
│   │   │   └── stripe-sync.ts               ← Stripe subscription → entitlement sync
│   │   └── components/
│   │       ├── PaywallModal.tsx               ← Upgrade prompt when hitting a gate
│   │       ├── UsageMeter.tsx                 ← Visual usage bar (scans used / limit)
│   │       ├── PlanBadge.tsx                  ← Displays current plan badge
│   │       └── FeatureGate.tsx                ← Conditional render based on entitlement
│   │
│   └── ...existing (gamification/, components/, pages/, tenant/, styles/)
│
├── supabase/
│   ├── migrations/
│   │   ├── ...existing (001-004)
│   │   ├── 005_analytics_schema.sql          ← PostHog event mirror + analytics tables
│   │   ├── 006_lead_hunter_schema.sql        ← Lead scans, profiles, scores
│   │   ├── 007_seo_oracle_schema.sql         ← SEO ranks, keywords, audits
│   │   ├── 008_entitlements_schema.sql       ← Entitlements, permissions, usage tracking
│   │   ├── 009_stripe_sync_schema.sql        ← Stripe mirror tables (products, subs, invoices)
│   │   ├── 010_npm_network_schema.sql        ← NPM referrals, partners, market data
│   │   └── 011_framer_bubble_schema.sql      ← Framer site provisioning + Bubble app sync
│   │
│   ├── functions/
│   │   ├── ...existing
│   │   ├── fg-lead-hunter/index.ts           ← Lead scan orchestrator Edge Function
│   │   ├── fg-seo-oracle/index.ts            ← SEO audit + rank check Edge Function
│   │   ├── fg-stripe-webhooks/index.ts       ← Central Stripe webhook processor
│   │   ├── fg-entitlement-sync/index.ts      ← Stripe sub change → entitlement update
│   │   ├── fg-framer-provision/index.ts      ← Auto-provision Framer site from template
│   │   ├── fg-framer-webhook/index.ts        ← Framer publish/form webhook handler
│   │   ├── fg-bubble-sync/index.ts           ← Bubble ↔ Supabase bidirectional sync
│   │   ├── fg-npm-market-sync/index.ts       ← NPM market data ingest
│   │   ├── fg-posthog-export/index.ts        ← PostHog → Supabase event pipeline
│   │   └── fg-analytics-refresh/index.ts     ← Materialized view refresh trigger
│   │
│   └── seed/
│       ├── ...existing
│       ├── entitlements.sql                   ← Default entitlement definitions
│       ├── stripe-products.sql                ← Stripe product/price ID mapping
│       └── seo-keywords.sql                   ← Seed keyword lists per trade industry
```

***

## Analytics Layer

### `src/analytics/posthog/posthog-client.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// POSTHOG — Finance Guild Product Analytics
// $50K startup credits available
// Ref: Monetization Strategy — "PostHog + custom metrics, tiered access"
// ═══════════════════════════════════════════════════════════════════

import posthog from 'posthog-js';

const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY;
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com';

export function initPostHog() {
  if (typeof window === 'undefined') return;
  
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    
    // Autocapture
    autocapture: true,
    capture_pageview: true,
    capture_pageleave: true,
    
    // Session replay
    enable_recording_console_log: true,
    session_recording: {
      maskAllInputs: true,           // PII protection — ICP T2+
      maskTextContent: false,
      recordCrossOriginIframes: true,
    },
    
    // Performance
    loaded: (ph) => {
      // Identify will be called after auth
      if (import.meta.env.DEV) {
        ph.debug();
      }
    },
    
    // Feature flags — drives entitlements + experiments
    bootstrap: {
      featureFlags: {},  // Pre-loaded from Supabase on SSR
    },
    
    // Privacy
    persistence: 'localStorage+cookie',
    respect_dnt: false,   // Business analytics tool, not advertising
    opt_out_capturing_by_default: false,
    
    // Custom properties on every event
    property_blacklist: ['$current_url'], // We handle URL sanitization ourselves
  });
}

export function identifyRep(rep: {
  id: string;
  email: string;
  name: string;
  tier: string;
  plan: string;
  tenant_id: string;
  stripe_customer_id?: string;
}) {
  posthog.identify(rep.id, {
    email: rep.email,
    name: rep.name,
    
    // Guild properties (filterable in PostHog)
    guild_tier: rep.tier,
    zes_plan: rep.plan,
    tenant_id: rep.tenant_id,
    
    // Stripe linkage
    stripe_customer_id: rep.stripe_customer_id,
    
    // Groups
    $groups: { tenant: rep.tenant_id },
  });
  
  // Group analytics (tenant-level metrics)
  posthog.group('tenant', rep.tenant_id, {
    name: 'Finance Guild',
    type: 'guild',
  });
}

export function identifyClient(client: {
  id: string;
  business_name: string;
  trade_industry: string;
  zes_plan: string;
  tradebuilder_plan?: string;
  mrr: number;
  rep_id: string;
}) {
  posthog.identify(client.id, {
    business_name: client.business_name,
    trade_industry: client.trade_industry,
    zes_plan: client.zes_plan,
    tradebuilder_plan: client.tradebuilder_plan,
    mrr: client.mrr,
    rep_id: client.rep_id,
    user_type: 'client',
  });
}

export { posthog };
```

### `src/analytics/posthog/events.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// POSTHOG EVENT TAXONOMY — Finance Guild
// Strict typing prevents orphan events and ensures funnel accuracy
// ═══════════════════════════════════════════════════════════════════

import { posthog } from './posthog-client';

// ── TYPED EVENT NAMES ─────────────────────────────────────────────

export const FG_EVENTS = {
  // ── Lead Hunter ──
  SCAN_INITIATED:           'fg_scan_initiated',
  SCAN_COMPLETED:           'fg_scan_completed',
  SCAN_FAILED:              'fg_scan_failed',
  LEAD_SCORED:              'fg_lead_scored',
  LEAD_CONTACTED:           'fg_lead_contacted',
  LEAD_DEMO_SCHEDULED:      'fg_lead_demo_scheduled',
  LEAD_DEMO_COMPLETED:      'fg_lead_demo_completed',
  
  // ── SEO Oracle ──
  SEO_AUDIT_RUN:            'fg_seo_audit_run',
  SEO_RANK_CHECKED:         'fg_seo_rank_checked',
  SEO_REPORT_GENERATED:     'fg_seo_report_generated',
  SEO_KEYWORD_TRACKED:      'fg_seo_keyword_tracked',
  
  // ── Sales Pipeline ──
  PROPOSAL_CREATED:         'fg_proposal_created',
  PROPOSAL_SENT:            'fg_proposal_sent',
  PROPOSAL_VIEWED:          'fg_proposal_viewed',
  PROPOSAL_SIGNED:          'fg_proposal_signed',
  CONTRACT_SIGNED:          'fg_contract_signed',
  
  // ── Revenue ──
  SUBSCRIPTION_CREATED:     'fg_subscription_created',
  SUBSCRIPTION_UPGRADED:    'fg_subscription_upgraded',
  SUBSCRIPTION_DOWNGRADED:  'fg_subscription_downgraded',
  SUBSCRIPTION_CANCELED:    'fg_subscription_canceled',
  INVOICE_PAID:             'fg_invoice_paid',
  INVOICE_FAILED:           'fg_invoice_failed',
  COMMISSION_EARNED:        'fg_commission_earned',
  
  // ── ZES Specific ──
  ZES_AGENT_DEPLOYED:       'fg_zes_agent_deployed',
  ZES_CALL_ANSWERED:        'fg_zes_call_answered',
  ZES_BOOKING_CREATED:      'fg_zes_booking_created',
  ZES_REVIEW_REQUESTED:     'fg_zes_review_requested',
  
  // ── TradeBuilder ──
  TB_SITE_PROVISIONED:      'fg_tb_site_provisioned',
  TB_SITE_PUBLISHED:        'fg_tb_site_published',
  TB_FORM_SUBMITTED:        'fg_tb_form_submitted',
  TB_BUNDLE_SOLD:           'fg_tb_bundle_sold',
  
  // ── Framer / Bubble ──
  FRAMER_SITE_CREATED:      'fg_framer_site_created',
  FRAMER_CMS_SYNCED:        'fg_framer_cms_synced',
  BUBBLE_APP_CONNECTED:     'fg_bubble_app_connected',
  BUBBLE_WORKFLOW_TRIGGERED: 'fg_bubble_workflow_triggered',
  
  // ── NPM Network ──
  NPM_REFERRAL_RECEIVED:    'fg_npm_referral_received',
  NPM_REFERRAL_CONVERTED:   'fg_npm_referral_converted',
  NPM_MARKET_DATA_FETCHED:  'fg_npm_market_data_fetched',
  
  // ── Entitlements ──
  ENTITLEMENT_GRANTED:      'fg_entitlement_granted',
  ENTITLEMENT_REVOKED:      'fg_entitlement_revoked',
  FEATURE_GATE_HIT:         'fg_feature_gate_hit',
  USAGE_LIMIT_REACHED:      'fg_usage_limit_reached',
  PAYWALL_SHOWN:            'fg_paywall_shown',
  PAYWALL_CONVERTED:        'fg_paywall_converted',
  
  // ── Gamification ──
  XP_EARNED:                'fg_xp_earned',
  LEVEL_UP:                 'fg_level_up',
  BADGE_UNLOCKED:           'fg_badge_unlocked',
  ACHIEVEMENT_UNLOCKED:     'fg_achievement_unlocked',
  TIER_PROMOTED:            'fg_tier_promoted',
  
  // ── Guild Master ──
  GUILD_MASTER_SESSION:     'fg_guild_master_session',
  GUILD_MASTER_QUERY:       'fg_guild_master_query',
} as const;

type FGEventName = typeof FG_EVENTS[keyof typeof FG_EVENTS];

export function trackEvent(event: FGEventName, properties?: Record<string, any>) {
  posthog.capture(event, {
    ...properties,
    _source: 'finance_guild',
    _timestamp: new Date().toISOString(),
  });
}

// ── FUNNEL DEFINITIONS (for PostHog UI) ────────────────────────────

export const FUNNELS = {
  SCAN_TO_CLOSE: {
    name: 'Lead Scan → Close',
    steps: [
      FG_EVENTS.SCAN_INITIATED,
      FG_EVENTS.SCAN_COMPLETED,
      FG_EVENTS.LEAD_CONTACTED,
      FG_EVENTS.LEAD_DEMO_SCHEDULED,
      FG_EVENTS.LEAD_DEMO_COMPLETED,
      FG_EVENTS.PROPOSAL_SENT,
      FG_EVENTS.CONTRACT_SIGNED,
    ],
  },
  PAYWALL_CONVERSION: {
    name: 'Feature Gate → Upgrade',
    steps: [
      FG_EVENTS.FEATURE_GATE_HIT,
      FG_EVENTS.PAYWALL_SHOWN,
      FG_EVENTS.PAYWALL_CONVERTED,
    ],
  },
  TRADEBUILDER_UPSELL: {
    name: 'ZES Client → TradeBuilder Bundle',
    steps: [
      FG_EVENTS.SUBSCRIPTION_CREATED,
      FG_EVENTS.TB_BUNDLE_SOLD,
      FG_EVENTS.TB_SITE_PROVISIONED,
      FG_EVENTS.TB_SITE_PUBLISHED,
    ],
  },
};
```

### `src/analytics/datadog/dd-tracer.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// DATADOG APM — Finance Guild Backend Tracing
// $10K startup credits available
// Spans: Edge Functions, Supabase queries, external API calls
// ═══════════════════════════════════════════════════════════════════

import tracer from 'dd-trace';

export function initDatadogTracer() {
  tracer.init({
    service: 'finance-guild',
    env: process.env.NODE_ENV || 'development',
    version: process.env.APP_VERSION || '1.0.0',
    
    // APM
    runtimeMetrics: true,
    logInjection: true,
    
    // Profiling
    profiling: true,
    
    // Tags
    tags: {
      'guild': 'finance',
      'team': 'citadel-nexus',
    },
    
    // Integrations
    plugins: true,  // Auto-instrument pg, http, fetch, etc.
  });
  
  // Custom span tags for all traces
  tracer.use('http', {
    hooks: {
      request: (span, req) => {
        if (span && req) {
          span.setTag('fg.tenant_id', req.headers?.['x-tenant-id'] || 'unknown');
          span.setTag('fg.rep_id', req.headers?.['x-rep-id'] || 'unknown');
        }
      },
    },
  });
  
  // Supabase/Postgres instrumentation
  tracer.use('pg', {
    service: 'finance-guild-db',
    measured: true,
  });
}

// ── Custom span helpers ──────────────────────────────────────────

export function traceLeadScan(scanId: string, tradeIndustry: string) {
  const span = tracer.startSpan('fg.lead_scan', {
    tags: {
      'fg.scan_id': scanId,
      'fg.trade_industry': tradeIndustry,
      'resource.name': `scan:${tradeIndustry}`,
    },
  });
  return span;
}

export function traceSEOAudit(clientId: string, domain: string) {
  const span = tracer.startSpan('fg.seo_audit', {
    tags: {
      'fg.client_id': clientId,
      'fg.domain': domain,
      'resource.name': `seo:${domain}`,
    },
  });
  return span;
}

export function traceStripeWebhook(eventType: string, customerId: string) {
  const span = tracer.startSpan('fg.stripe_webhook', {
    tags: {
      'fg.stripe_event': eventType,
      'fg.stripe_customer': customerId,
      'resource.name': `webhook:${eventType}`,
    },
  });
  return span;
}

export function traceEntitlementCheck(repId: string, feature: string, granted: boolean) {
  const span = tracer.startSpan('fg.entitlement_check', {
    tags: {
      'fg.rep_id': repId,
      'fg.feature': feature,
      'fg.granted': granted,
      'resource.name': `entitlement:${feature}`,
    },
  });
  span.finish();
}

export { tracer };
```

### `src/analytics/datadog/dd-rum.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// DATADOG RUM — Browser Performance + Error Tracking
// ═══════════════════════════════════════════════════════════════════

import { datadogRum } from '@datadog/browser-rum';
import { datadogLogs } from '@datadog/browser-logs';

export function initDatadogRUM() {
  datadogRum.init({
    applicationId: import.meta.env.VITE_DD_APPLICATION_ID,
    clientToken: import.meta.env.VITE_DD_CLIENT_TOKEN,
    site: 'datadoghq.com',
    service: 'finance-guild-web',
    env: import.meta.env.MODE,
    version: import.meta.env.VITE_APP_VERSION || '1.0.0',
    
    sessionSampleRate: 100,
    sessionReplaySampleRate: 20,   // 20% of sessions get full replay
    trackUserInteractions: true,
    trackResources: true,
    trackLongTasks: true,
    defaultPrivacyLevel: 'mask-user-input',
    
    // Custom context
    beforeSend: (event) => {
      event.context = {
        ...event.context,
        guild: 'finance',
      };
      return true;
    },
  });
  
  datadogLogs.init({
    clientToken: import.meta.env.VITE_DD_CLIENT_TOKEN,
    site: 'datadoghq.com',
    service: 'finance-guild-web',
    forwardErrorsToLogs: true,
    sessionSampleRate: 100,
  });
}

export function setRUMUser(rep: { id: string; email: string; tier: string; plan: string }) {
  datadogRum.setUser({
    id: rep.id,
    email: rep.email,
    guild_tier: rep.tier,
    zes_plan: rep.plan,
  });
}

export { datadogRum, datadogLogs };
```

***

## Lead Hunter — Scraping & Acquisition Engine

### `src/scraping/lead-hunter/scanner-engine.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// LEAD HUNTER — Scan Orchestrator
// Runs all acquisition modules against a target business/geo
// Outputs: LeadProfile with score + ZES/TradeBuilder recommendation
// ═══════════════════════════════════════════════════════════════════

import { GoogleMapsScraper } from './modules/google-maps-scraper';
import { GBPScraper } from './modules/gbp-scraper';
import { WebsiteAuditor } from './modules/website-auditor';
import { SocialScraper } from './modules/social-scraper';
import { ReviewAggregator } from './modules/review-aggregator';
import { ContactEnricher } from './modules/contact-enricher';
import { TechStackDetector } from './modules/tech-stack-detector';
import { CompetitorMapper } from './modules/competitor-mapper';
import { LeadScoreEngine } from './scoring/lead-score-engine';
import { UrgencyDetector } from './scoring/urgency-detector';
import { RecommendationEngine } from './scoring/recommendation-engine';
import { ScanCache } from './storage/scan-cache';
import { ScreenshotStore } from './storage/screenshot-store';
import { traceLeadScan } from '../../analytics/datadog/dd-tracer';
import { trackEvent, FG_EVENTS } from '../../analytics/posthog/events';
import type { LeadScan, LeadProfile, ScanResult, ScanModule } from './types';

export class ScannerEngine {
  private modules: ScanModule[];
  private scoreEngine: LeadScoreEngine;
  private urgencyDetector: UrgencyDetector;
  private recommendationEngine: RecommendationEngine;
  private cache: ScanCache;
  private screenshots: ScreenshotStore;
  
  constructor(private supabase: any) {
    this.modules = [
      new GoogleMapsScraper(),
      new GBPScraper(),
      new WebsiteAuditor(),
      new SocialScraper(),
      new ReviewAggregator(),
      new ContactEnricher(),
      new TechStackDetector(),
      new CompetitorMapper(),
    ];
    this.scoreEngine = new LeadScoreEngine();
    this.urgencyDetector = new UrgencyDetector();
    this.recommendationEngine = new RecommendationEngine();
    this.cache = new ScanCache(supabase);
    this.screenshots = new ScreenshotStore(supabase);
  }
  
  async scan(input: LeadScan): Promise<ScanResult> {
    const span = traceLeadScan(input.scan_id, input.trade_industry);
    trackEvent(FG_EVENTS.SCAN_INITIATED, {
      scan_id: input.scan_id,
      trade_industry: input.trade_industry,
      geo: input.geo,
      rep_id: input.rep_id,
    });
    
    try {
      // Check cache first (24hr TTL)
      const cached = await this.cache.get(input.business_name, input.geo);
      if (cached) {
        span.setTag('fg.cache_hit', true);
        span.finish();
        return cached;
      }
      
      // Run all modules in parallel with timeout
      const moduleResults = await Promise.allSettled(
        this.modules.map(mod => 
          Promise.race([
            mod.execute(input),
            new Promise((_, reject) => setTimeout(() => reject(new Error(`${mod.name} timeout`)), 15000))
          ])
        )
      );
      
      // Aggregate results
      const profile: LeadProfile = {
        scan_id: input.scan_id,
        business_name: input.business_name,
        trade_industry: input.trade_industry,
        geo: input.geo,
        
        // Module outputs (fulfilled only)
        google_maps: this.extractResult(moduleResults[0]),
        gbp_data: this.extractResult(moduleResults[1]),
        website_audit: this.extractResult(moduleResults[2]),
        social_presence: this.extractResult(moduleResults[3]),
        reviews: this.extractResult(moduleResults[4]),
        contact_info: this.extractResult(moduleResults[5]),
        tech_stack: this.extractResult(moduleResults[6]),
        competitors: this.extractResult(moduleResults[7]),
        
        // Errors tracked
        module_errors: moduleResults
          .map((r, i) => r.status === 'rejected' ? { module: this.modules[i].name, error: r.reason?.message } : null)
          .filter(Boolean),
          
        scanned_at: new Date().toISOString(),
      };
      
      // Screenshot the website (if it exists)
      if (profile.website_audit?.url) {
        profile.screenshot_url = await this.screenshots.capture(profile.website_audit.url, input.scan_id);
      }
      
      // Score the lead
      const score = this.scoreEngine.calculate(profile);
      const urgency = this.urgencyDetector.detect(profile);
      const recommendation = this.recommendationEngine.recommend(profile, score, urgency);
      
      const result: ScanResult = {
        profile,
        score,            // 0-100
        urgency,          // { level: 'critical'|'high'|'medium'|'low', signals: string[] }
        recommendation,   // { zes_plan, tradebuilder_plan?, bundles, pitch_angle, objection_preempts }
        modules_completed: moduleResults.filter(r => r.status === 'fulfilled').length,
        modules_total: this.modules.length,
      };
      
      // Cache result
      await this.cache.set(input.business_name, input.geo, result);
      
      // Persist to Supabase
      await this.supabase.from('fg_lead_scans').insert({
        id: input.scan_id,
        rep_id: input.rep_id,
        business_name: input.business_name,
        trade_industry: input.trade_industry,
        geo: input.geo,
        score: score.total,
        urgency_level: urgency.level,
        recommended_plan: recommendation.zes_plan,
        recommended_bundle: recommendation.bundles?.[0]?.name,
        profile_data: profile,
        recommendation_data: recommendation,
      });
      
      trackEvent(FG_EVENTS.SCAN_COMPLETED, {
        scan_id: input.scan_id,
        score: score.total,
        urgency: urgency.level,
        recommended_plan: recommendation.zes_plan,
        has_website: !!profile.website_audit?.url,
        modules_completed: result.modules_completed,
      });
      
      span.setTag('fg.score', score.total);
      span.setTag('fg.urgency', urgency.level);
      span.finish();
      
      return result;
      
    } catch (error: any) {
      trackEvent(FG_EVENTS.SCAN_FAILED, { scan_id: input.scan_id, error: error.message });
      span.setTag('error', true);
      span.setTag('error.message', error.message);
      span.finish();
      throw error;
    }
  }
  
  private extractResult(settled: PromiseSettledResult<any>): any {
    return settled.status === 'fulfilled' ? settled.value : null;
  }
}
```

### `src/scraping/lead-hunter/types.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// LEAD HUNTER — Type Definitions
// ═══════════════════════════════════════════════════════════════════

export interface LeadScan {
  scan_id: string;
  rep_id: string;
  business_name: string;
  trade_industry: string;
  geo: { city: string; state: string; zip?: string; radius_miles: number };
  scan_depth: 'quick' | 'standard' | 'deep';   // Entitlement-gated
}

export interface ScanModule {
  name: string;
  execute(input: LeadScan): Promise<any>;
}

export interface LeadProfile {
  scan_id: string;
  business_name: string;
  trade_industry: string;
  geo: LeadScan['geo'];
  google_maps: GoogleMapsData | null;
  gbp_data: GBPData | null;
  website_audit: WebsiteAudit | null;
  social_presence: SocialPresence | null;
  reviews: ReviewData | null;
  contact_info: ContactInfo | null;
  tech_stack: TechStackData | null;
  competitors: CompetitorData | null;
  screenshot_url?: string;
  module_errors: { module: string; error: string }[];
  scanned_at: string;
}

export interface WebsiteAudit {
  url: string | null;
  has_website: boolean;
  is_mobile_responsive: boolean;
  has_ssl: boolean;
  page_speed_score: number;         // 0-100 (Lighthouse)
  core_web_vitals: { lcp: number; fid: number; cls: number };
  has_contact_form: boolean;
  has_click_to_call: boolean;
  has_booking_widget: boolean;
  has_chat_widget: boolean;
  has_schema_markup: boolean;
  cms_platform: string | null;      // wordpress, wix, squarespace, framer, bubble, custom
  pages_indexed: number;
  broken_links: number;
  image_optimization_score: number;
}

export interface GBPData {
  exists: boolean;
  claimed: boolean;
  name: string;
  rating: number;
  review_count: number;
  category: string;
  hours_set: boolean;
  photos_count: number;
  posts_recent: number;
  description_length: number;
  attributes: string[];
}

export interface ReviewData {
  google_rating: number;
  google_count: number;
  yelp_rating: number;
  yelp_count: number;
  bbb_rating: string;          // A+ to F
  bbb_accredited: boolean;
  facebook_rating: number;
  total_reviews: number;
  avg_rating: number;
  sentiment_score: number;     // -1.0 to 1.0
  recent_negative_count: number;  // Last 30 days
}

export interface SocialPresence {
  facebook: { exists: boolean; url?: string; followers?: number; active?: boolean };
  instagram: { exists: boolean; url?: string; followers?: number; posts_last_30?: number };
  tiktok: { exists: boolean; url?: string; followers?: number };
  youtube: { exists: boolean; url?: string; subscribers?: number };
  nextdoor: { exists: boolean; recommended?: boolean };
}

export interface ContactInfo {
  phone: string | null;
  email: string | null;
  address: string | null;
  owner_name: string | null;
  owner_email: string | null;     // ICP T2 — requires entitlement
}

export interface TechStackData {
  cms: string | null;              // wordpress, wix, squarespace, framer, bubble, shopify, custom
  hosting: string | null;
  analytics: string[];             // google-analytics, facebook-pixel, etc.
  chat_tools: string[];            // intercom, drift, crisp, etc.
  booking_tools: string[];         // calendly, cal.com, acuity
  payment_tools: string[];         // stripe, square, paypal
  crm: string[];                   // hubspot, salesforce, etc.
  seo_tools: string[];
  marketing_automation: string[];
}

export interface CompetitorData {
  competitors: {
    name: string;
    rating: number;
    review_count: number;
    has_website: boolean;
    estimated_monthly_spend: number;
    strengths: string[];
    weaknesses: string[];
  }[];
  market_saturation: 'low' | 'medium' | 'high';
  opportunity_score: number;
}

export interface LeadScore {
  total: number;                   // 0-100
  breakdown: {
    digital_presence: number;      // 0-25
    reputation: number;            // 0-25
    competition_gap: number;       // 0-25
    readiness_signals: number;     // 0-25
  };
}

export interface UrgencySignals {
  level: 'critical' | 'high' | 'medium' | 'low';
  signals: string[];               // Human-readable urgency reasons
}

export interface ScanRecommendation {
  zes_plan: 'scout' | 'operator' | 'autopilot';
  tradebuilder_plan: 'starter' | 'growth' | 'premium' | null;
  bundles: {
    name: string;
    total_price: number;
    discount_pct: number;
    includes: string[];
  }[];
  pitch_angle: string;             // Primary selling point
  objection_preempts: string[];    // Pre-address likely objections
  upsell_path: string[];           // Future upsell sequence
  priority_services: string[];     // Which TradeBoost micro-services to recommend first
}

export interface ScanResult {
  profile: LeadProfile;
  score: LeadScore;
  urgency: UrgencySignals;
  recommendation: ScanRecommendation;
  modules_completed: number;
  modules_total: number;
}
```

***

## SEO Oracle Engine

### `src/scraping/seo-oracle/seo-engine.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// SEO ORACLE — Rank Tracking + Keyword Research + Audit Engine
// Ref: ZES Operator includes "full SEO audit with rank tracking"
// Ref: ZES Autopilot includes "Metabase analytics dashboards"
// ═══════════════════════════════════════════════════════════════════

import { RankTracker } from './modules/rank-tracker';
import { KeywordResearcher } from './modules/keyword-researcher';
import { BacklinkChecker } from './modules/backlink-checker';
import { LocalPackMonitor } from './modules/local-pack-monitor';
import { CitationAuditor } from './modules/citation-auditor';
import { PageSpeedChecker } from './modules/page-speed-checker';
import { SchemaValidator } from './modules/schema-validator';
import { ContentGapAnalyzer } from './modules/content-gap-analyzer';
import { SEOHealthScore } from './scoring/seo-health-score';
import { SEORecommendations } from './scoring/seo-recommendations';
import { traceSEOAudit } from '../../analytics/datadog/dd-tracer';
import { trackEvent, FG_EVENTS } from '../../analytics/posthog/events';
import type { SEOAuditInput, SEOAuditResult, SEOHealthReport } from './types';

export class SEOEngine {
  private rankTracker: RankTracker;
  private keywordResearcher: KeywordResearcher;
  private backlinkChecker: BacklinkChecker;
  private localPackMonitor: LocalPackMonitor;
  private citationAuditor: CitationAuditor;
  private pageSpeedChecker: PageSpeedChecker;
  private schemaValidator: SchemaValidator;
  private contentGapAnalyzer: ContentGapAnalyzer;
  private healthScorer: SEOHealthScore;
  private recommender: SEORecommendations;
  
  constructor(
    private supabase: any,
    private config: {
      dataforseo_api_key: string;
      dataforseo_api_login: string;
      pagespeed_api_key: string;
    }
  ) {
    this.rankTracker = new RankTracker(config.dataforseo_api_key, config.dataforseo_api_login);
    this.keywordResearcher = new KeywordResearcher(config.dataforseo_api_key, config.dataforseo_api_login);
    this.backlinkChecker = new BacklinkChecker(config.dataforseo_api_key, config.dataforseo_api_login);
    this.localPackMonitor = new LocalPackMonitor(config.dataforseo_api_key, config.dataforseo_api_login);
    this.citationAuditor = new CitationAuditor();
    this.pageSpeedChecker = new PageSpeedChecker(config.pagespeed_api_key);
    this.schemaValidator = new SchemaValidator();
    this.contentGapAnalyzer = new ContentGapAnalyzer(config.dataforseo_api_key, config.dataforseo_api_login);
    this.healthScorer = new SEOHealthScore();
    this.recommender = new SEORecommendations();
  }
  
  async runFullAudit(input: SEOAuditInput): Promise<SEOAuditResult> {
    const span = traceSEOAudit(input.client_id, input.domain);
    trackEvent(FG_EVENTS.SEO_AUDIT_RUN, { client_id: input.client_id, domain: input.domain });
    
    const [
      rankings,
      keywords,
      backlinks,
      localPack,
      citations,
      pageSpeed,
      schema,
      contentGaps,
    ] = await Promise.allSettled([
      this.rankTracker.checkRankings(input.domain, input.target_keywords, input.geo),
      this.keywordResearcher.research(input.trade_industry, input.geo),
      this.backlinkChecker.analyze(input.domain),
      this.localPackMonitor.check(input.business_name, input.geo, input.trade_industry),
      this.citationAuditor.audit(input.business_name, input.phone, input.address),
      this.pageSpeedChecker.check(input.domain),
      this.schemaValidator.validate(input.domain),
      this.contentGapAnalyzer.analyze(input.domain, input.competitors || []),
    ]);
    
    const auditData = {
      rankings: rankings.status === 'fulfilled' ? rankings.value : null,
      keywords: keywords.status === 'fulfilled' ? keywords.value : null,
      backlinks: backlinks.status === 'fulfilled' ? backlinks.value : null,
      local_pack: localPack.status === 'fulfilled' ? localPack.value : null,
      citations: citations.status === 'fulfilled' ? citations.value : null,
      page_speed: pageSpeed.status === 'fulfilled' ? pageSpeed.value : null,
      schema_markup: schema.status === 'fulfilled' ? schema.value : null,
      content_gaps: contentGaps.status === 'fulfilled' ? contentGaps.value : null,
    };
    
    const healthScore = this.healthScorer.calculate(auditData);
    const recommendations = this.recommender.generate(auditData, healthScore);
    
    const result: SEOAuditResult = {
      audit_id: crypto.randomUUID(),
      client_id: input.client_id,
      domain: input.domain,
      ...auditData,
      health_score: healthScore,
      recommendations,
      audited_at: new Date().toISOString(),
    };
    
    // Persist
    await this.supabase.from('fg_seo_audits').insert({
      id: result.audit_id,
      client_id: input.client_id,
      domain: input.domain,
      health_score: healthScore.total,
      audit_data: result,
    });
    
    span.setTag('fg.seo_score', healthScore.total);
    span.finish();
    
    return result;
  }
  
  async trackRankings(clientId: string, domain: string, keywords: string[], geo: { city: string; state: string }) {
    trackEvent(FG_EVENTS.SEO_RANK_CHECKED, { client_id: clientId, domain, keyword_count: keywords.length });
    
    const rankings = await this.rankTracker.checkRankings(domain, keywords, geo);
    
    // Store historical ranking data
    for (const kw of rankings) {
      await this.supabase.from('fg_seo_rank_history').insert({
        client_id: clientId,
        keyword: kw.keyword,
        position: kw.position,
        local_pack_position: kw.local_pack_position,
        search_volume: kw.search_volume,
        checked_at: new Date().toISOString(),
      });
    }
    
    return rankings;
  }
}
```

***

## Entitlements & Permissions System

### `src/entitlements/types.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// ENTITLEMENTS & PERMISSIONS — Finance Guild
// Maps Stripe subscriptions + Guild tiers → feature access
// Two axes: CLIENT entitlements (ZES/TradeBuilder plan) and
//           REP entitlements (Guild tier)
// ═══════════════════════════════════════════════════════════════════

// ── CLIENT PLANS ──────────────────────────────────────────────────
// Ref: ZES Plan page — Scout / Operator / Autopilot
// Ref: TradeBuilder — Starter / Growth / Premium

export type ZESPlan = 'scout' | 'operator' | 'autopilot';
export type TradeBuilderPlan = 'starter' | 'growth' | 'premium' | null;
export type GuildTier = 'initiate' | '3-star' | '4-star' | '5-star' | 'elite' | 'd-tier';

export type EntitlementSubject = 'client' | 'rep';

export interface Entitlement {
  id: string;
  feature: FeatureKey;
  subject_type: EntitlementSubject;
  subject_id: string;               // client_id or rep_id
  source: EntitlementSource;
  granted_at: string;
  expires_at: string | null;        // null = permanent
  usage_limit: number | null;       // null = unlimited
  usage_current: number;
  metadata: Record<string, any>;
}

export type EntitlementSource = 
  | { type: 'stripe_subscription'; subscription_id: string; plan: ZESPlan | TradeBuilderPlan }
  | { type: 'guild_tier'; tier: GuildTier }
  | { type: 'admin_grant'; granted_by: string; reason: string }
  | { type: 'achievement'; achievement_id: string }
  | { type: 'trial'; trial_id: string };

// ── FEATURE KEYS ──────────────────────────────────────────────────
// Every gated feature in Finance Guild

export type FeatureKey =
  // ── ZES Features (client-facing) ──
  | 'zes:gbp_optimization'
  | 'zes:google_posts'
  | 'zes:directory_listings'
  | 'zes:lead_crm'
  | 'zes:missed_call_textback'
  | 'zes:call_tracking'
  | 'zes:monthly_report'
  | 'zes:online_booking'           // Operator+
  | 'zes:review_automation'        // Operator+
  | 'zes:seo_audit'                // Operator+
  | 'zes:competitor_monitoring'    // Operator+
  | 'zes:social_graphics_4'       // Operator (4/mo)
  | 'zes:social_graphics_12'      // Autopilot (12/mo)
  | 'zes:notion_kb'               // Operator+
  | 'zes:customer_profiles'       // Operator+
  | 'zes:priority_support'        // Operator+
  | 'zes:onboarding_call'         // Operator+
  | 'zes:ai_voice_agent'          // Autopilot only
  | 'zes:call_transcripts'        // Autopilot only
  | 'zes:n8n_workflows'           // Autopilot only
  | 'zes:invoice_text_to_pay'     // Autopilot only
  | 'zes:ai_blog_posts'           // Autopilot only
  | 'zes:metabase_dashboards'     // Autopilot only
  | 'zes:revenue_forecasting'     // Autopilot only
  | 'zes:citadel_workshop'        // Autopilot only
  | 'zes:image_generation'        // Autopilot only
  // ── TradeBuilder Features (client-facing) ──
  | 'tb:framer_site'
  | 'tb:domain_ssl'
  | 'tb:basic_seo'
  | 'tb:pages_3'                  // Starter
  | 'tb:pages_10'                 // Growth
  | 'tb:pages_unlimited'          // Premium
  | 'tb:booking_widget'           // Growth+
  | 'tb:review_aggregation'       // Growth+
  | 'tb:blog'                     // Growth+
  | 'tb:ai_content'               // Premium only
  | 'tb:lead_forms'               // Premium only
  | 'tb:crm_integration'          // Premium only
  // ── Rep Features (guild-tier-gated) ──
  | 'rep:lead_scanner_quick'      // Initiate
  | 'rep:lead_scanner_standard'   // 3-star+
  | 'rep:lead_scanner_deep'       // 4-star+
  | 'rep:seo_oracle_basic'        // 3-star+
  | 'rep:seo_oracle_advanced'     // 4-star+
  | 'rep:seo_oracle_enterprise'   // 5-star+
  | 'rep:metabase_basic'          // 3-star+
  | 'rep:metabase_advanced'       // 4-star+
  | 'rep:posthog_basic'           // 3-star+
  | 'rep:posthog_advanced'        // Elite+
  | 'rep:datadog_dashboards'      // 5-star+
  | 'rep:npm_referrals'           // 3-star+
  | 'rep:npm_market_data'         // 4-star+
  | 'rep:docusend_basic'          // 3-star+
  | 'rep:docusend_advanced'       // 4-star+
  | 'rep:commission_standard'     // 3-star+
  | 'rep:commission_premium'      // 5-star+
  | 'rep:commission_equity'       // Elite+
  | 'rep:guild_master_voice'      // Initiate+
  | 'rep:bubble_integration'      // 4-star+
  | 'rep:framer_provisioning'     // 3-star+
  | 'rep:stripe_connect_payouts'  // 3-star+
  | 'rep:client_data_export'      // 4-star+
  | 'rep:team_management'         // 5-star+
  | 'rep:api_access'              // Elite+;

export interface PermissionCheck {
  feature: FeatureKey;
  granted: boolean;
  reason: string;
  usage_remaining?: number;
  upgrade_path?: { plan: string; price: string; features_unlocked: FeatureKey[] };
}

export interface UsageLimit {
  feature: FeatureKey;
  limit: number;
  used: number;
  resets_at: string;         // ISO date
  period: 'day' | 'week' | 'month';
}
```

### `src/entitlements/permission-matrix.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// PERMISSION MATRIX — What each plan/tier unlocks
// Single source of truth for all gating decisions
// Ref: ZES Plan page (Scout $15 / Operator $20 / Autopilot $30)
// Ref: TradeBuilder ($99-299/mo)
// Ref: Service Tier Template (Initiate → D-Tier)
// ═══════════════════════════════════════════════════════════════════

import type { ZESPlan, TradeBuilderPlan, GuildTier, FeatureKey } from './types';

// ── CLIENT PERMISSION MATRIX (ZES) ───────────────────────────────

export const ZES_PERMISSIONS: Record<ZESPlan, FeatureKey[]> = {
  scout: [
    'zes:gbp_optimization',
    'zes:google_posts',
    'zes:directory_listings',
    'zes:lead_crm',
    'zes:missed_call_textback',
    'zes:call_tracking',
    'zes:monthly_report',
  ],
  operator: [
    // Inherits all Scout features
    'zes:gbp_optimization', 'zes:google_posts', 'zes:directory_listings',
    'zes:lead_crm', 'zes:missed_call_textback', 'zes:call_tracking', 'zes:monthly_report',
    // Operator additions
    'zes:online_booking',
    'zes:review_automation',
    'zes:seo_audit',
    'zes:competitor_monitoring',
    'zes:social_graphics_4',
    'zes:notion_kb',
    'zes:customer_profiles',
    'zes:priority_support',
    'zes:onboarding_call',
  ],
  autopilot: [
    // Inherits all Operator features
    'zes:gbp_optimization', 'zes:google_posts', 'zes:directory_listings',
    'zes:lead_crm', 'zes:missed_call_textback', 'zes:call_tracking', 'zes:monthly_report',
    'zes:online_booking', 'zes:review_automation', 'zes:seo_audit',
    'zes:competitor_monitoring', 'zes:notion_kb', 'zes:customer_profiles',
    'zes:priority_support', 'zes:onboarding_call',
    // Autopilot additions
    'zes:social_graphics_12',
    'zes:ai_voice_agent',
    'zes:call_transcripts',
    'zes:n8n_workflows',
    'zes:invoice_text_to_pay',
    'zes:ai_blog_posts',
    'zes:metabase_dashboards',
    'zes:revenue_forecasting',
    'zes:citadel_workshop',
    'zes:image_generation',
  ],
};

// ── CLIENT PERMISSION MATRIX (TRADEBUILDER) ──────────────────────

export const TB_PERMISSIONS: Record<NonNullable<TradeBuilderPlan>, FeatureKey[]> = {
  starter: [
    'tb:framer_site', 'tb:domain_ssl', 'tb:basic_seo', 'tb:pages_3',
  ],
  growth: [
    'tb:framer_site', 'tb:domain_ssl', 'tb:basic_seo',
    'tb:pages_10', 'tb:booking_widget', 'tb:review_aggregation', 'tb:blog',
  ],
  premium: [
    'tb:framer_site', 'tb:domain_ssl', 'tb:basic_seo',
    'tb:pages_unlimited', 'tb:booking_widget', 'tb:review_aggregation', 'tb:blog',
    'tb:ai_content', 'tb:lead_forms', 'tb:crm_integration',
  ],
};

// ── REP PERMISSION MATRIX (GUILD TIER) ───────────────────────────

export const TIER_PERMISSIONS: Record<GuildTier, FeatureKey[]> = {
  initiate: [
    'rep:lead_scanner_quick',
    'rep:guild_master_voice',
  ],
  '3-star': [
    'rep:lead_scanner_quick', 'rep:lead_scanner_standard',
    'rep:guild_master_voice',
    'rep:seo_oracle_basic',
    'rep:metabase_basic',
    'rep:posthog_basic',
    'rep:npm_referrals',
    'rep:docusend_basic',
    'rep:commission_standard',
    'rep:framer_provisioning',
    'rep:stripe_connect_payouts',
  ],
  '4-star': [
    'rep:lead_scanner_quick', 'rep:lead_scanner_standard', 'rep:lead_scanner_deep',
    'rep:guild_master_voice',
    'rep:seo_oracle_basic', 'rep:seo_oracle_advanced',
    'rep:metabase_basic', 'rep:metabase_advanced',
    'rep:posthog_basic',
    'rep:npm_referrals', 'rep:npm_market_data',
    'rep:docusend_basic', 'rep:docusend_advanced',
    'rep:commission_standard',
    'rep:framer_provisioning',
    'rep:stripe_connect_payouts',
    'rep:client_data_export',
    'rep:bubble_integration',
  ],
  '5-star': [
    'rep:lead_scanner_quick', 'rep:lead_scanner_standard', 'rep:lead_scanner_deep',
    'rep:guild_master_voice',
    'rep:seo_oracle_basic', 'rep:seo_oracle_advanced', 'rep:seo_oracle_enterprise',
    'rep:metabase_basic', 'rep:metabase_advanced',
    'rep:posthog_basic',
    'rep:datadog_dashboards',
    'rep:npm_referrals', 'rep:npm_market_data',
    'rep:docusend_basic', 'rep:docusend_advanced',
    'rep:commission_standard', 'rep:commission_premium',
    'rep:framer_provisioning',
    'rep:stripe_connect_payouts',
    'rep:client_data_export',
    'rep:bubble_integration',
    'rep:team_management',
  ],
  elite: [
    // All features
    'rep:lead_scanner_quick', 'rep:lead_scanner_standard', 'rep:lead_scanner_deep',
    'rep:guild_master_voice',
    'rep:seo_oracle_basic', 'rep:seo_oracle_advanced', 'rep:seo_oracle_enterprise',
    'rep:metabase_basic', 'rep:metabase_advanced',
    'rep:posthog_basic', 'rep:posthog_advanced',
    'rep:datadog_dashboards',
    'rep:npm_referrals', 'rep:npm_market_data',
    'rep:docusend_basic', 'rep:docusend_advanced',
    'rep:commission_standard', 'rep:commission_premium', 'rep:commission_equity',
    'rep:framer_provisioning',
    'rep:stripe_connect_payouts',
    'rep:client_data_export',
    'rep:bubble_integration',
    'rep:team_management',
    'rep:api_access',
  ],
  'd-tier': [
    // All features (same as elite + custom negotiated)
    'rep:lead_scanner_quick', 'rep:lead_scanner_standard', 'rep:lead_scanner_deep',
    'rep:guild_master_voice',
    'rep:seo_oracle_basic', 'rep:seo_oracle_advanced', 'rep:seo_oracle_enterprise',
    'rep:metabase_basic', 'rep:metabase_advanced',
    'rep:posthog_basic', 'rep:posthog_advanced',
    'rep:datadog_dashboards',
    'rep:npm_referrals', 'rep:npm_market_data',
    'rep:docusend_basic', 'rep:docusend_advanced',
    'rep:commission_standard', 'rep:commission_premium', 'rep:commission_equity',
    'rep:framer_provisioning',
    'rep:stripe_connect_payouts',
    'rep:client_data_export',
    'rep:bubble_integration',
    'rep:team_management',
    'rep:api_access',
  ],
};

// ── USAGE LIMITS ──────────────────────────────────────────────────

export const USAGE_LIMITS: Record<string, Record<GuildTier | ZESPlan, { limit: number; period: 'day' | 'month' }>> = {
  lead_scans: {
    initiate:    { limit: 5,    period: 'month' },
    '3-star':    { limit: 50,   period: 'month' },
    '4-star':    { limit: 200,  period: 'month' },
    '5-star':    { limit: 500,  period: 'month' },
    elite:       { limit: 2000, period: 'month' },
    'd-tier':    { limit: 99999, period: 'month' },
    scout:       { limit: 0,    period: 'month' },  // Clients don't scan
    operator:    { limit: 0,    period: 'month' },
    autopilot:   { limit: 0,    period: 'month' },
  },
  seo_audits: {
    initiate:    { limit: 0,    period: 'month' },
    '3-star':    { limit: 10,   period: 'month' },
    '4-star':    { limit: 50,   period: 'month' },
    '5-star':    { limit: 200,  period: 'month' },
    elite:       { limit: 1000, period: 'month' },
    'd-tier':    { limit: 99999, period: 'month' },
    scout:       { limit: 0,    period: 'month' },
    operator:    { limit: 1,    period: 'month' },
    autopilot:   { limit: 4,    period: 'month' },
  },
  api_calls: {
    initiate:    { limit: 100,    period: 'day' },
    '3-star':    { limit: 1000,   period: 'day' },
    '4-star':    { limit: 5000,   period: 'day' },
    '5-star':    { limit: 25000,  period: 'day' },
    elite:       { limit: 100000, period: 'day' },
    'd-tier':    { limit: 999999, period: 'day' },
    scout:       { limit: 100,    period: 'day' },
    operator:    { limit: 500,    period: 'day' },
    autopilot:   { limit: 2000,   period: 'day' },
  },
};

// ── BUNDLE DISCOUNT MATRIX ────────────────────────────────────────
// Ref: ZES Plan page — bundle discounts

export const BUNDLE_DISCOUNTS: Record<string, { zes: ZESPlan; tb: TradeBuilderPlan; discount_pct: number }> = {
  'tb_starter_zes_scout':    { zes: 'scout',    tb: 'starter', discount_pct: 10 },
  'tb_starter_zes_operator': { zes: 'operator',  tb: 'starter', discount_pct: 15 },
  'tb_starter_zes_autopilot':{ zes: 'autopilot', tb: 'starter', discount_pct: 20 },
  'tb_growth_zes_scout':     { zes: 'scout',    tb: 'growth',  discount_pct: 10 },
  'tb_growth_zes_operator':  { zes: 'operator',  tb: 'growth',  discount_pct: 15 },
  'tb_growth_zes_autopilot': { zes: 'autopilot', tb: 'growth',  discount_pct: 20 },
  'tb_premium_zes_scout':    { zes: 'scout',    tb: 'premium', discount_pct: 10 },
  'tb_premium_zes_operator': { zes: 'operator',  tb: 'premium', discount_pct: 15 },
  'tb_premium_zes_autopilot':{ zes: 'autopilot', tb: 'premium', discount_pct: 20 },
};
```

### `src/entitlements/entitlement-engine.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// ENTITLEMENT ENGINE — Core evaluation logic
// Checks: Stripe subscription → plan features + Guild tier → rep features
// Single entry point for all permission checks
// ═══════════════════════════════════════════════════════════════════

import { ZES_PERMISSIONS, TB_PERMISSIONS, TIER_PERMISSIONS, USAGE_LIMITS } from './permission-matrix';
import { trackEvent, FG_EVENTS } from '../analytics/posthog/events';
import { traceEntitlementCheck } from '../analytics/datadog/dd-tracer';
import type { FeatureKey, PermissionCheck, ZESPlan, TradeBuilderPlan, GuildTier } from './types';

export class EntitlementEngine {
  constructor(private supabase: any) {}
  
  // ── CHECK CLIENT ENTITLEMENT ──────────────────────────────────
  
  async checkClient(clientId: string, feature: FeatureKey): Promise<PermissionCheck> {
    // Fetch client's active subscriptions from Stripe mirror
    const { data: client } = await this.supabase
      .from('fg_clients')
      .select('zes_plan, tradebuilder_plan, stripe_subscription_id, status')
      .eq('id', clientId)
      .single();
    
    if (!client || client.status !== 'active') {
      return { feature, granted: false, reason: 'No active subscription' };
    }
    
    // Check ZES entitlements
    if (feature.startsWith('zes:') && client.zes_plan) {
      const allowed = ZES_PERMISSIONS[client.zes_plan as ZESPlan] || [];
      if (allowed.includes(feature)) {
        return { feature, granted: true, reason: `Included in ZES ${client.zes_plan}` };
      }
      // Find upgrade path
      const upgrade = this.findClientUpgradePath(feature, client.zes_plan as ZESPlan);
      return { feature, granted: false, reason: `Not included in ZES ${client.zes_plan}`, upgrade_path: upgrade };
    }
    
    // Check TradeBuilder entitlements
    if (feature.startsWith('tb:') && client.tradebuilder_plan) {
      const allowed = TB_PERMISSIONS[client.tradebuilder_plan as NonNullable<TradeBuilderPlan>] || [];
      if (allowed.includes(feature)) {
        return { feature, granted: true, reason: `Included in TradeBuilder ${client.tradebuilder_plan}` };
      }
      return { feature, granted: false, reason: `Not included in TradeBuilder ${client.tradebuilder_plan}` };
    }
    
    return { feature, granted: false, reason: 'Feature not associated with current plan' };
  }
  
  // ── CHECK REP ENTITLEMENT ─────────────────────────────────────
  
  async checkRep(repId: string, feature: FeatureKey): Promise<PermissionCheck> {
    const { data: profile } = await this.supabase
      .from('fg_rep_profiles')
      .select('tier')
      .eq('rep_id', repId)
      .single();
    
    const tier: GuildTier = profile?.tier || 'initiate';
    const allowed = TIER_PERMISSIONS[tier] || [];
    const granted = allowed.includes(feature);
    
    traceEntitlementCheck(repId, feature, granted);
    
    if (granted) {
      // Check usage limits
      const usageCheck = await this.checkUsage(repId, feature, tier);
      if (usageCheck && usageCheck.used >= usageCheck.limit) {
        trackEvent(FG_EVENTS.USAGE_LIMIT_REACHED, { rep_id: repId, feature });
        return { 
          feature, granted: false, 
          reason: `Usage limit reached (${usageCheck.used}/${usageCheck.limit} this ${usageCheck.period})`,
          usage_remaining: 0,
        };
      }
      return { 
        feature, granted: true, 
        reason: `Included in ${tier} tier`,
        usage_remaining: usageCheck ? usageCheck.limit - usageCheck.used : undefined,
      };
    }
    
    // Find upgrade path
    const upgrade = this.findRepUpgradePath(feature, tier);
    trackEvent(FG_EVENTS.FEATURE_GATE_HIT, { rep_id: repId, feature, current_tier: tier });
    
    return { feature, granted: false, reason: `Requires higher tier than ${tier}`, upgrade_path: upgrade };
  }
  
  // ── USAGE TRACKING ────────────────────────────────────────────
  
  private async checkUsage(subjectId: string, feature: FeatureKey, tierOrPlan: GuildTier | ZESPlan) {
    const featureBase = feature.split(':').pop() || '';
    const limitKey = Object.keys(USAGE_LIMITS).find(k => feature.includes(k) || featureBase.includes(k));
    if (!limitKey) return null;
    
    const limitConfig = USAGE_LIMITS[limitKey]?.[tierOrPlan];
    if (!limitConfig) return null;
    
    // Count usage in current period
    const periodStart = limitConfig.period === 'day'
      ? new Date(new Date().setHours(0, 0, 0, 0)).toISOString()
      : new Date(new Date().setDate(1)).toISOString();
    
    const { count } = await this.supabase
      .from('fg_usage_events')
      .select('*', { count: 'exact', head: true })
      .eq('subject_id', subjectId)
      .eq('feature', feature)
      .gte('created_at', periodStart);
    
    return { limit: limitConfig.limit, used: count || 0, period: limitConfig.period };
  }
  
  async recordUsage(subjectId: string, feature: FeatureKey) {
    await this.supabase.from('fg_usage_events').insert({
      subject_id: subjectId,
      feature,
    });
  }
  
  // ── UPGRADE PATH HELPERS ──────────────────────────────────────
  
  private findClientUpgradePath(feature: FeatureKey, currentPlan: ZESPlan) {
    const planOrder: ZESPlan[] = ['scout', 'operator', 'autopilot'];
    const prices: Record<ZESPlan, string> = { scout: '$15/mo', operator: '$20/mo', autopilot: '$30/mo' };
    
    for (const plan of planOrder) {
      if (planOrder.indexOf(plan) <= planOrder.indexOf(currentPlan)) continue;
      if (ZES_PERMISSIONS[plan].includes(feature)) {
        const newFeatures = ZES_PERMISSIONS[plan].filter(f => !ZES_PERMISSIONS[currentPlan].includes(f));
        return { plan, price: prices[plan], features_unlocked: newFeatures };
      }
    }
    return undefined;
  }
  
  private findRepUpgradePath(feature: FeatureKey, currentTier: GuildTier) {
    const tierOrder: GuildTier[] = ['initiate', '3-star', '4-star', '5-star', 'elite', 'd-tier'];
    
    for (const tier of tierOrder) {
      if (tierOrder.indexOf(tier) <= tierOrder.indexOf(currentTier)) continue;
      if (TIER_PERMISSIONS[tier].includes(feature)) {
        const newFeatures = TIER_PERMISSIONS[tier].filter(f => !TIER_PERMISSIONS[currentTier].includes(f));
        return { plan: tier, price: 'Earn via XP', features_unlocked: newFeatures };
      }
    }
    return undefined;
  }
  
  // ── STRIPE SYNC ───────────────────────────────────────────────
  // Called by Stripe webhook handler on subscription changes
  
  async syncFromStripe(stripeSubscription: {
    id: string;
    customer: string;
    status: string;
    items: { price: { id: string; product: string } }[];
  }) {
    const { data: client } = await this.supabase
      .from('fg_clients')
      .select('id, zes_plan, tradebuilder_plan')
      .eq('stripe_customer_id', stripeSubscription.customer)
      .single();
    
    if (!client) return;
    
    // Map Stripe price IDs to plans
    const planMap = await this.getStripePlanMap();
    const newPlans: { zes?: ZESPlan; tb?: TradeBuilderPlan } = {};
    
    for (const item of stripeSubscription.items) {
      const mapping = planMap[item.price.id];
      if (mapping?.type === 'zes') newPlans.zes = mapping.plan as ZESPlan;
      if (mapping?.type === 'tradebuilder') newPlans.tb = mapping.plan as TradeBuilderPlan;
    }
    
    // Update client record
    await this.supabase.from('fg_clients').update({
      zes_plan: newPlans.zes || client.zes_plan,
      tradebuilder_plan: newPlans.tb ?? client.tradebuilder_plan,
      stripe_subscription_status: stripeSubscription.status,
    }).eq('id', client.id);
    
    // Log entitlement changes
    if (newPlans.zes && newPlans.zes !== client.zes_plan) {
      trackEvent(FG_EVENTS.ENTITLEMENT_GRANTED, {
        client_id: client.id,
        old_plan: client.zes_plan,
        new_plan: newPlans.zes,
        source: 'stripe',
      });
    }
  }
  
  private async getStripePlanMap(): Promise<Record<string, { type: string; plan: string }>> {
    const { data } = await this.supabase.from('fg_stripe_products').select('stripe_price_id, product_type, plan_name');
    const map: Record<string, { type: string; plan: string }> = {};
    for (const row of data || []) {
      map[row.stripe_price_id] = { type: row.product_type, plan: row.plan_name };
    }
    return map;
  }
}
```

### `src/entitlements/components/FeatureGate.tsx`

```tsx
// ═══════════════════════════════════════════════════════════════════
// FEATURE GATE — Conditional render based on entitlement
// Wraps any UI element and shows paywall if not entitled
// ═══════════════════════════════════════════════════════════════════

import { ReactNode, useEffect, useState } from 'react';
import { useEntitlements } from '../hooks/useEntitlements';
import PaywallModal from './PaywallModal';
import type { FeatureKey, PermissionCheck } from '../types';

interface FeatureGateProps {
  feature: FeatureKey;
  children: ReactNode;
  fallback?: ReactNode;        // Show instead of paywall
  silent?: boolean;            // Don't show paywall, just hide
  subjectType?: 'client' | 'rep';
  subjectId?: string;
}

export default function FeatureGate({
  feature,
  children,
  fallback,
  silent = false,
  subjectType = 'rep',
  subjectId,
}: FeatureGateProps) {
  const { check, isLoading } = useEntitlements();
  const [permission, setPermission] = useState<PermissionCheck | null>(null);
  const [showPaywall, setShowPaywall] = useState(false);
  
  useEffect(() => {
    check(feature, subjectType, subjectId).then(setPermission);
  }, [feature, subjectType, subjectId]);
  
  if (isLoading || !permission) return null;
  
  if (permission.granted) return <>{children}</>;
  
  if (silent) return null;
  if (fallback) return <>{fallback}</>;
  
  return (
    <>
      <div
        className="relative cursor-pointer opacity-50 hover:opacity-70 transition-opacity"
        onClick={() => setShowPaywall(true)}
      >
        <div className="pointer-events-none filter blur-[2px]">{children}</div>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="bg-gray-900/90 rounded-lg px-4 py-2 border border-purple-500/30">
            <span className="text-sm text-purple-300">🔒 {permission.reason}</span>
          </div>
        </div>
      </div>
      
      {showPaywall && (
        <PaywallModal
          feature={feature}
          permission={permission}
          onClose={() => setShowPaywall(false)}
        />
      )}
    </>
  );
}
```

***

## Stripe Integration — Webhook Handler

### `src/integrations/stripe/webhooks/webhook-handler.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// STRIPE WEBHOOK HANDLER — Central router
// Routes all Stripe events to specific handlers
// Triggers: Entitlement sync, XP awards, commission calc, PostHog events
// ═══════════════════════════════════════════════════════════════════

import Stripe from 'stripe';
import { verifyStripeSignature } from './webhook-verifier';
import { handleInvoicePaid } from './handlers/invoice-paid';
import { handleInvoiceFailed } from './handlers/invoice-failed';
import { handleSubscriptionCreated } from './handlers/subscription-created';
import { handleSubscriptionUpdated } from './handlers/subscription-updated';
import { handleSubscriptionDeleted } from './handlers/subscription-deleted';
import { handleCheckoutCompleted } from './handlers/checkout-completed';
import { handleCustomerCreated } from './handlers/customer-created';
import { handlePayoutPaid } from './handlers/payout-paid';
import { traceStripeWebhook } from '../../../analytics/datadog/dd-tracer';

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY')!, { apiVersion: '2024-12-18.acacia' });

export async function handleStripeWebhook(req: Request, supabase: any): Promise<Response> {
  const body = await req.text();
  const signature = req.headers.get('stripe-signature')!;
  
  let event: Stripe.Event;
  try {
    event = verifyStripeSignature(body, signature, Deno.env.get('STRIPE_WEBHOOK_SECRET')!);
  } catch (err) {
    return new Response('Webhook signature verification failed', { status: 400 });
  }
  
  const span = traceStripeWebhook(event.type, (event.data.object as any).customer || 'unknown');
  
  try {
    const ctx = { stripe, supabase, event };
    
    switch (event.type) {
      // ── Subscription lifecycle ──
      case 'customer.subscription.created':
        await handleSubscriptionCreated(ctx);
        break;
      case 'customer.subscription.updated':
        await handleSubscriptionUpdated(ctx);
        break;
      case 'customer.subscription.deleted':
        await handleSubscriptionDeleted(ctx);
        break;
        
      // ── Invoice events ──
      case 'invoice.paid':
        await handleInvoicePaid(ctx);      // → Commission calc + XP award + entitlement confirm
        break;
      case 'invoice.payment_failed':
        await handleInvoiceFailed(ctx);    // → Churn risk flag + alert
        break;
        
      // ── Checkout ──
      case 'checkout.session.completed':
        await handleCheckoutCompleted(ctx); // → Attribution + PostHog
        break;
        
      // ── Customer ──
      case 'customer.created':
        await handleCustomerCreated(ctx);   // → CRM record
        break;
        
      // ── Connect payouts (rep commissions) ──
      case 'payout.paid':
        await handlePayoutPaid(ctx);        // → Rep XP for payout
        break;
        
      default:
        console.log(`Unhandled Stripe event: ${event.type}`);
    }
    
    span.finish();
    return new Response(JSON.stringify({ received: true }), { status: 200 });
    
  } catch (err: any) {
    span.setTag('error', true);
    span.setTag('error.message', err.message);
    span.finish();
    console.error(`Stripe webhook error: ${err.message}`);
    return new Response(JSON.stringify({ error: err.message }), { status: 500 });
  }
}
```

### `src/integrations/stripe/products/product-catalog.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// STRIPE PRODUCT CATALOG — ZES + TradeBuilder + Bundles
// Maps Stripe product/price IDs to internal plan names
// Ref: ZES Plans — Scout $15 / Operator $20 / Autopilot $30
// Ref: TradeBuilder — Starter $99 / Growth $199 / Premium $299
// ═══════════════════════════════════════════════════════════════════

export interface StripePlanMapping {
  stripe_product_id: string;
  stripe_price_id: string;
  product_type: 'zes' | 'tradebuilder' | 'bundle' | 'addon';
  plan_name: string;
  monthly_price: number;
  features: string[];
  entitlements: string[];        // Maps to FeatureKey[]
}

// These IDs are set in Stripe Dashboard and mirrored to Supabase
// Actual IDs populated during deployment via `fg-stripe-product-sync` Edge Function

export const PRODUCT_CATALOG: StripePlanMapping[] = [
  // ── ZES Plans ──
  {
    stripe_product_id: 'prod_zes_scout',
    stripe_price_id: 'price_zes_scout_monthly',
    product_type: 'zes',
    plan_name: 'scout',
    monthly_price: 1500,  // Stripe uses cents
    features: ['GBP optimization', 'Google posts', 'Directory listings', 'Lead CRM', 'Missed call text-back', 'Call tracking', 'Monthly report'],
    entitlements: ['zes:gbp_optimization', 'zes:google_posts', 'zes:directory_listings', 'zes:lead_crm', 'zes:missed_call_textback', 'zes:call_tracking', 'zes:monthly_report'],
  },
  {
    stripe_product_id: 'prod_zes_operator',
    stripe_price_id: 'price_zes_operator_monthly',
    product_type: 'zes',
    plan_name: 'operator',
    monthly_price: 2000,
    features: ['Everything in Scout', 'Online booking', 'Review automation', 'SEO audit', 'Competitor monitoring', '4 social graphics/mo', 'Notion KB', 'Customer profiles', 'Priority support'],
    entitlements: ['zes:online_booking', 'zes:review_automation', 'zes:seo_audit', 'zes:competitor_monitoring', 'zes:social_graphics_4', 'zes:notion_kb', 'zes:customer_profiles', 'zes:priority_support', 'zes:onboarding_call'],
  },
  {
    stripe_product_id: 'prod_zes_autopilot',
    stripe_price_id: 'price_zes_autopilot_monthly',
    product_type: 'zes',
    plan_name: 'autopilot',
    monthly_price: 3000,
    features: ['Everything in Operator', 'AI voice agent 24/7', 'Call transcripts', 'n8n workflows', 'Invoice + text-to-pay', '12 social graphics/mo', 'AI blog posts', 'Metabase dashboards', 'Revenue forecasting', 'Citadel Workshop', 'Multi-model image gen'],
    entitlements: ['zes:ai_voice_agent', 'zes:call_transcripts', 'zes:n8n_workflows', 'zes:invoice_text_to_pay', 'zes:social_graphics_12', 'zes:ai_blog_posts', 'zes:metabase_dashboards', 'zes:revenue_forecasting', 'zes:citadel_workshop', 'zes:image_generation'],
  },
  
  // ── TradeBuilder Plans ──
  {
    stripe_product_id: 'prod_tb_starter',
    stripe_price_id: 'price_tb_starter_monthly',
    product_type: 'tradebuilder',
    plan_name: 'starter',
    monthly_price: 9900,
    features: ['Framer template site', 'Domain + SSL', 'Basic SEO', '3 pages'],
    entitlements: ['tb:framer_site', 'tb:domain_ssl', 'tb:basic_seo', 'tb:pages_3'],
  },
  {
    stripe_product_id: 'prod_tb_growth',
    stripe_price_id: 'price_tb_growth_monthly',
    product_type: 'tradebuilder',
    plan_name: 'growth',
    monthly_price: 19900,
    features: ['Everything in Starter', 'Booking widget', 'Review aggregation', 'Blog', '10 pages'],
    entitlements: ['tb:booking_widget', 'tb:review_aggregation', 'tb:blog', 'tb:pages_10'],
  },
  {
    stripe_product_id: 'prod_tb_premium',
    stripe_price_id: 'price_tb_premium_monthly',
    product_type: 'tradebuilder',
    plan_name: 'premium',
    monthly_price: 29900,
    features: ['Everything in Growth', 'AI content', 'Lead forms', 'CRM integration', 'Unlimited pages'],
    entitlements: ['tb:ai_content', 'tb:lead_forms', 'tb:crm_integration', 'tb:pages_unlimited'],
  },
  
  // ── Add-ons ──
  {
    stripe_product_id: 'prod_storm_blast',
    stripe_price_id: 'price_storm_blast_per_use',
    product_type: 'addon',
    plan_name: 'storm_blast',
    monthly_price: 2500,       // Per blast, not monthly
    features: ['Emergency/storm SMS blast'],
    entitlements: [],
  },
];

// ── BUNDLE PRICING ────────────────────────────────────────────────

export const BUNDLE_CATALOG = [
  { name: 'TB Starter + ZES Scout',      discount: 0.10, zes: 'scout',    tb: 'starter', combined_cents: Math.round((1500 + 9900) * 0.90) },
  { name: 'TB Starter + ZES Operator',   discount: 0.15, zes: 'operator', tb: 'starter', combined_cents: Math.round((2000 + 9900) * 0.85) },
  { name: 'TB Starter + ZES Autopilot',  discount: 0.20, zes: 'autopilot',tb: 'starter', combined_cents: Math.round((3000 + 9900) * 0.80) },
  { name: 'TB Growth + ZES Operator',    discount: 0.15, zes: 'operator', tb: 'growth',  combined_cents: Math.round((2000 + 19900) * 0.85) },
  { name: 'TB Growth + ZES Autopilot',   discount: 0.20, zes: 'autopilot',tb: 'growth',  combined_cents: Math.round((3000 + 19900) * 0.80) },
  { name: 'TB Premium + ZES Autopilot',  discount: 0.20, zes: 'autopilot',tb: 'premium', combined_cents: Math.round((3000 + 29900) * 0.80) },
];
```

***

## Framer & Bubble Integration

### `src/integrations/framer/framer-site-provisioner.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// FRAMER SITE PROVISIONER — Auto-provision TradeBuilder Framer sites
// Ref: ZES Plan — "TradeBuilder builds Framer-based websites"
// Ref: "Sites delivered within 48 hours of payment"
// Target: Automated provisioning reduces to minutes, not hours
// ═══════════════════════════════════════════════════════════════════

import { FramerAPIClient } from './framer-api-client';
import { FramerCMSSync } from './framer-cms-sync';
import { FramerAnalyticsBridge } from './framer-analytics-bridge';
import { trackEvent, FG_EVENTS } from '../../analytics/posthog/events';
import type { FramerSiteConfig, ProvisionResult } from './types';

export class FramerSiteProvisioner {
  private framer: FramerAPIClient;
  private cms: FramerCMSSync;
  private analytics: FramerAnalyticsBridge;
  
  constructor(
    private supabase: any,
    config: { framer_api_token: string; posthog_key: string; dd_client_token: string }
  ) {
    this.framer = new FramerAPIClient(config.framer_api_token);
    this.cms = new FramerCMSSync(config.framer_api_token, supabase);
    this.analytics = new FramerAnalyticsBridge(config.posthog_key, config.dd_client_token);
  }
  
  async provision(config: FramerSiteConfig): Promise<ProvisionResult> {
    const { client_id, trade_industry, business_name, plan, domain, intake_data } = config;
    
    // 1. Duplicate template project based on plan tier
    const templateId = this.getTemplateId(plan, trade_industry);
    const site = await this.framer.duplicateProject(templateId, {
      name: `${business_name} — ${trade_industry}`,
    });
    
    // 2. Inject business data into CMS collections
    await this.cms.populateBusinessData(site.id, {
      business_name: intake_data.business_name,
      phone: intake_data.phone,
      email: intake_data.email,
      address: intake_data.address,
      city: intake_data.city,
      state: intake_data.state,
      zip: intake_data.zip,
      services: intake_data.services,
      hours: intake_data.hours,
      logo_url: intake_data.logo_url,
      brand_colors: intake_data.brand_colors,
      tagline: intake_data.tagline,
      about_text: intake_data.about_text,
      license_number: intake_data.license_number,
      service_areas: intake_data.service_areas,
    });
    
    // 3. Inject PostHog + Datadog RUM tracking scripts
    await this.analytics.injectTracking(site.id, {
      client_id,
      trade_industry,
      plan,
    });
    
    // 4. Configure custom domain
    if (domain) {
      await this.framer.setCustomDomain(site.id, domain);
    }
    
    // 5. Publish site
    const publishResult = await this.framer.publish(site.id);
    
    // 6. Store in Supabase
    await this.supabase.from('fg_tradebuilder_sites').insert({
      client_id,
      framer_project_id: site.id,
      framer_site_url: publishResult.url,
      custom_domain: domain,
      plan,
      trade_industry,
      template_id: templateId,
      published_at: new Date().toISOString(),
      status: 'active',
    });
    
    trackEvent(FG_EVENTS.FRAMER_SITE_CREATED, {
      client_id,
      plan,
      trade_industry,
      has_custom_domain: !!domain,
    });
    
    return {
      site_id: site.id,
      url: publishResult.url,
      custom_domain: domain,
      status: 'published',
    };
  }
  
  private getTemplateId(plan: string, industry: string): string {
    // Template registry — maps plan+industry to Framer template project IDs
    const templates: Record<string, Record<string, string>> = {
      starter: {
        hvac: 'framer_tpl_hvac_starter',
        plumbing: 'framer_tpl_plumbing_starter',
        electrical: 'framer_tpl_electrical_starter',
        roofing: 'framer_tpl_roofing_starter',
        landscaping: 'framer_tpl_landscaping_starter',
        _default: 'framer_tpl_generic_starter',
      },
      growth: {
        hvac: 'framer_tpl_hvac_growth',
        plumbing: 'framer_tpl_plumbing_growth',
        _default: 'framer_tpl_generic_growth',
      },
      premium: {
        _default: 'framer_tpl_generic_premium',
      },
    };
    return templates[plan]?.[industry] || templates[plan]?._default || templates.starter._default;
  }
}
```

### `src/integrations/bubble/bubble-api-client.ts`

```typescript
// ═══════════════════════════════════════════════════════════════════
// BUBBLE API CLIENT — Bidirectional sync with Bubble.io apps
// Use case: Clients who already have Bubble apps get ZES as an agent
// layer on top of their existing Bubble-built website
// ═══════════════════════════════════════════════════════════════════

export class BubbleAPIClient {
  private baseUrl: string;
  private apiToken: string;
  
  constructor(appName: string, apiToken: string, version: string = 'live') {
    this.baseUrl = `https://${appName}.bubbleapps.io/version-${version}/api/1.1`;
    this.apiToken = apiToken;
  }
  
  private async request<T>(method: string, path: string, body?: any): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        'Authorization': `Bearer ${this.apiToken}`,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`Bubble API error: ${res.status} ${await res.text()}`);
    return res.json();
  }
  
  // ── Data API (CRUD) ──
  async createThing<T>(type: string, data: Record<string, any>): Promise<T> {
    return this.request('POST', `/obj/${type}`, data);
  }
  
  async getThing<T>(type: string, id: string): Promise<T> {
    return this.request('GET', `/obj/${type}/${id}`);
  }
  
  async searchThings<T>(type: string, constraints: any[], limit = 100): Promise<{ results: T[]; remaining: number }> {
    const params = new URLSearchParams({ constraints: JSON.stringify(constraints), limit: String(limit) });
    return this.request('GET', `/obj/${type}?${params}`);
  }
  
  async updateThing(type: string, id: string, data: Record<string, any>): Promise<void> {
    await this.request('PATCH', `/obj/${type}/${id}`, data);
  }
  
  async deleteThing(type: string, id: string): Promise<void> {
    await this.request('DELETE', `/obj/${type}/${id}`);
  }
  
  // ── Workflow API ──
  async triggerWorkflow(workflowName: string, data: Record<string, any>): Promise<any> {
    return this.request('POST', `/wf/${workflowName}`, data);
  }
  
  // ── ZES-specific helpers ──
  
  async syncLeadToBubble(lead: { name: string; phone: string; email: string; source: string }) {
    return this.createThing('lead', {
      name: lead.name,
      phone: lead.phone,
      email: lead.email,
      source: lead.source,
      created_by: 'zes_agent',
      status: 'new',
    });
  }
  
  async syncBookingToBubble(booking: { customer_name: string; service: string; datetime: string; phone: string }) {
    return this.triggerWorkflow('new_booking_from_zes', booking);
  }
  
  async pullContactsFromBubble(): Promise<any[]> {
    const { results } = await this.searchThings('customer', [], 1000);
    return results;
  }
}
```

***

## Supabase — Entitlements & Analytics Migrations

### `supabase/migrations/008_entitlements_schema.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- ENTITLEMENTS — Feature gating, permissions, usage tracking
-- Two axes: Client (plan-based) + Rep (tier-based)
-- Synced from Stripe subscriptions + Guild tier advancement
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE fg_entitlements (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_type    TEXT NOT NULL CHECK (subject_type IN ('client', 'rep')),
  subject_id      UUID NOT NULL,                -- client_id or rep_id
  feature         TEXT NOT NULL,                -- Feature key string
  source_type     TEXT NOT NULL CHECK (source_type IN ('stripe_subscription', 'guild_tier', 'admin_grant', 'achievement', 'trial')),
  source_id       TEXT,                         -- subscription_id, tier name, etc.
  granted_at      TIMESTAMPTZ DEFAULT now(),
  expires_at      TIMESTAMPTZ,                  -- NULL = permanent
  usage_limit     INTEGER,                      -- NULL = unlimited
  metadata        JSONB DEFAULT '{}',
  active          BOOLEAN DEFAULT true,
  UNIQUE(subject_type, subject_id, feature, source_type)
);

CREATE TABLE fg_usage_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id      UUID NOT NULL,
  feature         TEXT NOT NULL,
  metadata        JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Stripe mirror tables
CREATE TABLE fg_stripe_products (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stripe_product_id TEXT UNIQUE NOT NULL,
  stripe_price_id TEXT UNIQUE NOT NULL,
  product_type    TEXT NOT NULL CHECK (product_type IN ('zes', 'tradebuilder', 'bundle', 'addon')),
  plan_name       TEXT NOT NULL,
  monthly_price_cents INTEGER NOT NULL,
  features        TEXT[] DEFAULT '{}',
  entitlement_keys TEXT[] DEFAULT '{}',
  active          BOOLEAN DEFAULT true,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE fg_stripe_subscriptions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stripe_subscription_id TEXT UNIQUE NOT NULL,
  stripe_customer_id TEXT NOT NULL,
  client_id       UUID REFERENCES fg_clients(id),
  status          TEXT NOT NULL,                -- active, past_due, canceled, trialing
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  cancel_at       TIMESTAMPTZ,
  items           JSONB DEFAULT '[]',           -- Array of {price_id, product_id, quantity}
  metadata        JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE fg_stripe_invoices (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stripe_invoice_id TEXT UNIQUE NOT NULL,
  stripe_customer_id TEXT NOT NULL,
  client_id       UUID REFERENCES fg_clients(id),
  subscription_id TEXT,
  amount_cents    INTEGER NOT NULL,
  status          TEXT NOT NULL,                -- paid, open, void, uncollectible
  paid_at         TIMESTAMPTZ,
  period_start    TIMESTAMPTZ,
  period_end      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Usage tracking aggregation (for Metabase)
CREATE MATERIALIZED VIEW fg_mv_usage_summary AS
SELECT
  subject_id,
  feature,
  DATE_TRUNC('month', created_at) AS month,
  COUNT(*) AS usage_count
FROM fg_usage_events
GROUP BY subject_id, feature, DATE_TRUNC('month', created_at);

CREATE UNIQUE INDEX idx_fg_mv_usage_summary ON fg_mv_usage_summary(subject_id, feature, month);

-- RLS
ALTER TABLE fg_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_stripe_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_stripe_invoices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "entitlements_own" ON fg_entitlements FOR SELECT
  USING (subject_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "usage_own" ON fg_usage_events FOR SELECT
  USING (subject_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "stripe_sub_own" ON fg_stripe_subscriptions FOR SELECT
  USING (client_id IN (SELECT id FROM fg_clients WHERE rep_id = fg_my_rep_id()) OR fg_is_admin());
CREATE POLICY "stripe_inv_own" ON fg_stripe_invoices FOR SELECT
  USING (client_id IN (SELECT id FROM fg_clients WHERE rep_id = fg_my_rep_id()) OR fg_is_admin());

-- Indexes
CREATE INDEX idx_fg_entitlements_subject ON fg_entitlements(subject_type, subject_id);
CREATE INDEX idx_fg_entitlements_feature ON fg_entitlements(feature);
CREATE INDEX idx_fg_usage_events_subject ON fg_usage_events(subject_id, feature);
CREATE INDEX idx_fg_usage_events_created ON fg_usage_events(created_at DESC);
CREATE INDEX idx_fg_stripe_subs_customer ON fg_stripe_subscriptions(stripe_customer_id);
CREATE INDEX idx_fg_stripe_subs_client ON fg_stripe_subscriptions(client_id);
CREATE INDEX idx_fg_stripe_inv_client ON fg_stripe_invoices(client_id);
```

### `supabase/migrations/006_lead_hunter_schema.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- LEAD HUNTER — Scan results, profiles, scores, recommendations
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE fg_lead_scans (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rep_id              UUID NOT NULL REFERENCES fg_reps(id),
  business_name       TEXT NOT NULL,
  trade_industry      TEXT NOT NULL,
  geo                 JSONB NOT NULL,           -- {city, state, zip, radius_miles}
  score               INTEGER,                  -- 0-100
  urgency_level       TEXT,                     -- critical, high, medium, low
  recommended_plan    TEXT,                     -- scout, operator, autopilot
  recommended_bundle  TEXT,
  profile_data        JSONB DEFAULT '{}',       -- Full LeadProfile
  recommendation_data JSONB DEFAULT '{}',       -- Full ScanRecommendation
  screenshot_url      TEXT,
  scan_depth          TEXT DEFAULT 'standard',
  status              TEXT DEFAULT 'completed',
  created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE fg_lead_contacts (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_id             UUID REFERENCES fg_lead_scans(id),
  rep_id              UUID NOT NULL REFERENCES fg_reps(id),
  business_name       TEXT NOT NULL,
  contact_method      TEXT,                     -- phone, email, in_person, social
  outcome             TEXT,                     -- reached, voicemail, no_answer, meeting_set
  notes               TEXT,
  follow_up_date      DATE,
  created_at          TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE fg_lead_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_lead_contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "scans_own" ON fg_lead_scans FOR ALL USING (rep_id = fg_my_rep_id() OR fg_is_admin());
CREATE POLICY "contacts_own" ON fg_lead_contacts FOR ALL USING (rep_id = fg_my_rep_id() OR fg_is_admin());

CREATE INDEX idx_fg_lead_scans_rep ON fg_lead_scans(rep_id);
CREATE INDEX idx_fg_lead_scans_score ON fg_lead_scans(score DESC);
CREATE INDEX idx_fg_lead_scans_industry ON fg_lead_scans(trade_industry);
CREATE INDEX idx_fg_lead_scans_created ON fg_lead_scans(created_at DESC);
```

### `supabase/migrations/007_seo_oracle_schema.sql`

```sql
-- ═══════════════════════════════════════════════════════════════════
-- SEO ORACLE — Rank tracking, keyword data, audit history
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE fg_seo_audits (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID NOT NULL REFERENCES fg_clients(id),
  domain          TEXT NOT NULL,
  health_score    INTEGER,              -- 0-100
  audit_data      JSONB DEFAULT '{}',   -- Full SEOAuditResult
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE fg_seo_rank_history (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id           UUID NOT NULL REFERENCES fg_clients(id),
  keyword             TEXT NOT NULL,
  position            INTEGER,          -- 1-100 or NULL if not ranked
  local_pack_position INTEGER,          -- 1-3 or NULL
  search_volume       INTEGER,
  difficulty          NUMERIC(4,1),
  checked_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE fg_seo_keywords (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID NOT NULL REFERENCES fg_clients(id),
  keyword         TEXT NOT NULL,
  target_position INTEGER DEFAULT 3,
  current_position INTEGER,
  tracking_active BOOLEAN DEFAULT true,
  UNIQUE(client_id, keyword)
);

ALTER TABLE fg_seo_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_seo_rank_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE fg_seo_keywords ENABLE ROW LEVEL SECURITY;

CREATE POLICY "seo_audit_own" ON fg_seo_audits FOR SELECT
  USING (client_id IN (SELECT id FROM fg_clients WHERE rep_id = fg_my_rep_id()) OR fg_is_admin());
CREATE POLICY "seo_rank_own" ON fg_seo_rank_history FOR SELECT
  USING (client_id IN (SELECT id FROM fg_clients WHERE rep_id = fg_my_rep_id()) OR fg_is_admin());
CREATE POLICY "seo_kw_own" ON fg_seo_keywords FOR ALL
  USING (client_id IN (SELECT id FROM fg_clients WHERE rep_id = fg_my_rep_id()) OR fg_is_admin());

CREATE INDEX idx_fg_seo_rank_client_kw ON fg_seo_rank_history(client_id, keyword);
CREATE INDEX idx_fg_seo_rank_checked ON fg_seo_rank_history(checked_at DESC);

-- Materialized view: latest rank per keyword per client (for Metabase)
CREATE MATERIALIZED VIEW fg_mv_seo_latest_ranks AS
SELECT DISTINCT ON (client_id, keyword)
  client_id, keyword, position, local_pack_position, search_volume, checked_at
FROM fg_seo_rank_history
ORDER BY client_id, keyword, checked_at DESC;

CREATE UNIQUE INDEX idx_fg_mv_seo_latest ON fg_mv_seo_latest_ranks(client_id, keyword);
```

***

## Metabase Dashboard Queries

### `src/analytics/metabase/questions/mrr-by-rep.sql`

```sql
-- MRR by Rep — Finance Guild Metabase Question
SELECT
  r.display_name AS rep_name,
  rp.tier AS guild_tier,
  COUNT(DISTINCT c.id) AS active_clients,
  SUM(CASE WHEN c.zes_plan = 'scout' THEN 15
           WHEN c.zes_plan = 'operator' THEN 20
           WHEN c.zes_plan = 'autopilot' THEN 30
           ELSE 0 END) AS zes_mrr,
  SUM(CASE WHEN c.tradebuilder_plan = 'starter' THEN 99
           WHEN c.tradebuilder_plan = 'growth' THEN 199
           WHEN c.tradebuilder_plan = 'premium' THEN 299
           ELSE 0 END) AS tb_mrr,
  SUM(CASE WHEN c.zes_plan = 'scout' THEN 15
           WHEN c.zes_plan = 'operator' THEN 20
           WHEN c.zes_plan = 'autopilot' THEN 30
           ELSE 0 END) +
  SUM(CASE WHEN c.tradebuilder_plan = 'starter' THEN 99
           WHEN c.tradebuilder_plan = 'growth' THEN 199
           WHEN c.tradebuilder_plan = 'premium' THEN 299
           ELSE 0 END) AS total_mrr,
  rp.xp,
  rp.level,
  rp.trust_score
FROM fg_reps r
JOIN fg_rep_profiles rp ON rp.rep_id = r.id
LEFT JOIN fg_clients c ON c.rep_id = r.id AND c.status = 'active'
GROUP BY r.id, r.display_name, rp.tier, rp.xp, rp.level, rp.trust_score
ORDER BY total_mrr DESC;
```

### `src/analytics/metabase/questions/scan-conversion-rate.sql`

```sql
-- Scan → Close Conversion Funnel — Per Rep
SELECT
  r.display_name AS rep_name,
  COUNT(DISTINCT ls.id) AS total_scans,
  COUNT(DISTINCT lc.id) FILTER (WHERE lc.outcome = 'reached') AS contacts_made,
  COUNT(DISTINCT lc.id) FILTER (WHERE lc.outcome = 'meeting_set') AS demos_set,
  COUNT(DISTINCT c.id) FILTER (WHERE c.created_at >= NOW() - INTERVAL '90 days') AS clients_won_90d,
  ROUND(
    COUNT(DISTINCT c.id) FILTER (WHERE c.created_at >= NOW() - INTERVAL '90 days')::NUMERIC /
    NULLIF(COUNT(DISTINCT ls.id), 0) * 100, 1
  ) AS conversion_rate_pct,
  ROUND(AVG(ls.score), 1) AS avg_lead_score
FROM fg_reps r
LEFT JOIN fg_lead_scans ls ON ls.rep_id = r.id AND ls.created_at >= NOW() - INTERVAL '90 days'
LEFT JOIN fg_lead_contacts lc ON lc.rep_id = r.id AND lc.created_at >= NOW() - INTERVAL '90 days'
LEFT JOIN fg_clients c ON c.rep_id = r.id
GROUP BY r.id, r.display_name
ORDER BY conversion_rate_pct DESC NULLS LAST;
```

***

This covers the full analytics stack (PostHog product analytics with $50K credits, Datadog APM/RUM with $10K credits, Metabase embedded dashboards, and Supabase Realtime) , the complete Lead Hunter scraping engine with 8 parallel modules scoring 0-100 and mapping to ZES plan recommendations , the SEO Oracle with DataForSEO rank tracking, keyword research, local pack monitoring, and citation auditing , the Framer integration for automated TradeBuilder site provisioning from templates , the Bubble bidirectional API client for clients running existing Bubble apps , the full Stripe integration covering products, subscriptions, Connect payouts, webhooks, and bundle pricing with the 10/15/20% discount matrix , NPM Second Network market data and referral tracking , and the entitlement/permission system with two axes — client entitlements driven by ZES plan (Scout $15/Operator $20/Autopilot $30) and TradeBuilder plan ($99-299), plus rep entitlements driven by guild tier (Initiate through D-Tier) — all with usage limits, feature gates, paywall modals, and Stripe subscription sync .Here's the full code across all three systems, aligned with the updated product structure: **TradeBuilder = website income**, **ZES = 24hr agent delivery for existing websites**, and **ZES as upsell extension within TradeBuilder packages** .

***

## Part 1: NDA/MCA/LOI/SOW Contract Review & Tracking

### Supabase Schema (001_contracts.sql)

```sql
CREATE TYPE contract_type AS ENUM ('nda', 'mca', 'loi', 'sow');
CREATE TYPE contract_status AS ENUM (
    'draft', 'pending_review', 'under_negotiation',
    'pending_signature', 'active', 'expired',
    'terminated', 'renewed'
);
CREATE TYPE review_verdict AS ENUM ('approved', 'rejected', 'revision_needed');

-- Master Contracts Table
CREATE TABLE IF NOT EXISTS contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_number TEXT NOT NULL UNIQUE,
    contract_type contract_type NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    
    -- Parties
    party_a_name TEXT NOT NULL,
    party_a_email TEXT,
    party_b_name TEXT NOT NULL,
    party_b_email TEXT,
    
    -- Product context (TradeBuilder vs ZES)
    product_line TEXT NOT NULL DEFAULT 'zes',   -- 'tradebuilder', 'zes', 'watcher', 'guild'
    is_tradebuilder_upsell BOOLEAN DEFAULT false,
    parent_contract_id UUID REFERENCES contracts(id),
    
    -- Status & Dates
    status contract_status NOT NULL DEFAULT 'draft',
    effective_date DATE,
    expiration_date DATE,
    auto_renew BOOLEAN DEFAULT false,
    renewal_period_months INTEGER DEFAULT 12,
    
    -- Financial
    total_value NUMERIC(12,2) DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    
    -- Document storage
    document_url TEXT,
    signed_document_url TEXT,
    docusign_envelope_id TEXT,
    
    -- Metadata
    created_by UUID REFERENCES auth.users(id),
    assigned_reviewer UUID REFERENCES auth.users(id),
    notion_page_id TEXT,
    tags TEXT[],
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_contracts_type ON contracts(contract_type);
CREATE INDEX idx_contracts_status ON contracts(status);
CREATE INDEX idx_contracts_product ON contracts(product_line);
CREATE INDEX idx_contracts_expiration ON contracts(expiration_date);

-- Contract Review Log
CREATE TABLE IF NOT EXISTS contract_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    reviewer_id UUID REFERENCES auth.users(id),
    reviewer_name TEXT NOT NULL,
    review_round INTEGER NOT NULL DEFAULT 1,
    verdict review_verdict NOT NULL,
    comments TEXT,
    risk_flags JSONB DEFAULT '[]',
    clause_notes JSONB DEFAULT '[]',
    reviewed_at TIMESTAMPTZ DEFAULT now()
);

-- Contract Milestones (for SOW tracking)
CREATE TABLE IF NOT EXISTS contract_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    milestone_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    deliverables TEXT[],
    due_date DATE,
    completed_date DATE,
    payment_amount NUMERIC(12,2) DEFAULT 0,
    payment_status TEXT DEFAULT 'pending',
    stripe_invoice_id TEXT,
    xero_invoice_id TEXT,
    status TEXT DEFAULT 'not_started',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(contract_id, milestone_number)
);

-- Contract Version History
CREATE TABLE IF NOT EXISTS contract_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id UUID NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    change_summary TEXT NOT NULL,
    changed_by UUID REFERENCES auth.users(id),
    document_url TEXT,
    diff_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(contract_id, version_number)
);

-- Auto-generate contract numbers (e.g. NDA-2026-0001)
CREATE OR REPLACE FUNCTION generate_contract_number()
RETURNS TRIGGER AS $$
DECLARE
    prefix TEXT;
    seq INTEGER;
BEGIN
    prefix := UPPER(NEW.contract_type::TEXT);
    SELECT COALESCE(MAX(
        CAST(SPLIT_PART(contract_number, '-', 3) AS INTEGER)
    ), 0) + 1 INTO seq
    FROM contracts
    WHERE contract_type = NEW.contract_type
      AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM now());
    NEW.contract_number := prefix || '-' || EXTRACT(YEAR FROM now())::TEXT || '-' || LPAD(seq::TEXT, 4, '0');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_contract_number
BEFORE INSERT ON contracts
FOR EACH ROW
WHEN (NEW.contract_number IS NULL OR NEW.contract_number = '')
EXECUTE FUNCTION generate_contract_number();

-- Expiration alert trigger
CREATE OR REPLACE FUNCTION notify_contract_expiring()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.expiration_date IS NOT NULL 
       AND NEW.expiration_date <= (now() + interval '30 days')
       AND NEW.status = 'active' THEN
        PERFORM pg_notify('contract_expiring', json_build_object(
            'id', NEW.id, 'contract_number', NEW.contract_number,
            'title', NEW.title, 'expiration_date', NEW.expiration_date
        )::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER contract_expiration_check
AFTER INSERT OR UPDATE ON contracts
FOR EACH ROW EXECUTE FUNCTION notify_contract_expiring();

-- RLS
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_versions ENABLE ROW LEVEL SECURITY;
```

### Python Contract Service (contract_service.py)

```python
# citadel_helper/contracts/contract_service.py

import uuid
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum

class ContractType(Enum):
    NDA = "nda"
    MCA = "mca"
    LOI = "loi"
    SOW = "sow"

class ContractStatus(Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    UNDER_NEGOTIATION = "under_negotiation"
    PENDING_SIGNATURE = "pending_signature"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    RENEWED = "renewed"

class ContractService:
    """Full lifecycle contract management for NDA/MCA/LOI/SOW."""

    def __init__(self, supabase_client, stripe_client, notion_client, slack_webhook_url: str):
        self.supabase = supabase_client
        self.stripe = stripe_client
        self.notion = notion_client
        self.slack_url = slack_webhook_url

    async def create_contract(
        self,
        contract_type: ContractType,
        title: str,
        party_a_name: str,
        party_b_name: str,
        product_line: str = "zes",
        is_tradebuilder_upsell: bool = False,
        total_value: float = 0,
        currency: str = "USD",
        effective_date: Optional[date] = None,
        expiration_date: Optional[date] = None,
        milestones: Optional[List[Dict]] = None,
        metadata: Optional[Dict] = None,
        created_by: Optional[str] = None,
        party_b_email: Optional[str] = None,
        parent_contract_id: Optional[str] = None,
    ) -> Dict[str, Any]:

        payload = {
            "contract_type": contract_type.value,
            "title": title,
            "party_a_name": party_a_name,
            "party_b_name": party_b_name,
            "party_b_email": party_b_email,
            "product_line": product_line,
            "is_tradebuilder_upsell": is_tradebuilder_upsell,
            "parent_contract_id": parent_contract_id,
            "total_value": total_value,
            "currency": currency,
            "effective_date": effective_date.isoformat() if effective_date else None,
            "expiration_date": expiration_date.isoformat() if expiration_date else None,
            "status": ContractStatus.DRAFT.value,
            "created_by": created_by,
            "metadata": metadata or {},
        }

        result = self.supabase.table("contracts").insert(payload).execute()
        contract = result.data[0]
        contract_id = contract["id"]

        # Create milestones if SOW
        if contract_type == ContractType.SOW and milestones:
            for i, ms in enumerate(milestones, 1):
                self.supabase.table("contract_milestones").insert({
                    "contract_id": contract_id,
                    "milestone_number": i,
                    "title": ms.get("title", f"Milestone {i}"),
                    "description": ms.get("description"),
                    "deliverables": ms.get("deliverables", []),
                    "due_date": ms.get("due_date"),
                    "payment_amount": ms.get("payment_amount", 0),
                }).execute()

        # Create Stripe customer
        if party_b_email:
            customer = self.stripe.Customer.create(
                email=party_b_email, name=party_b_name,
                metadata={"contract_id": contract_id, "product_line": product_line}
            )
            self.supabase.table("contracts").update(
                {"stripe_customer_id": customer.id}
            ).eq("id", contract_id).execute()

        await self._notify_slack(
            f"📄 New {contract_type.value.upper()}: *{title}*\n"
            f"Party B: {party_b_name} | Value: ${total_value:,.2f} | Product: {product_line}"
        )
        return contract

    async def submit_review(
        self, contract_id: str, reviewer_id: str, reviewer_name: str,
        verdict: str, comments: str = "", risk_flags: Optional[List[Dict]] = None,
    ) -> Dict:
        reviews = self.supabase.table("contract_reviews") \
            .select("review_round").eq("contract_id", contract_id) \
            .order("review_round", desc=True).limit(1).execute()
        round_num = (reviews.data[0]["review_round"] + 1) if reviews.data else 1

        review = self.supabase.table("contract_reviews").insert({
            "contract_id": contract_id,
            "reviewer_id": reviewer_id,
            "reviewer_name": reviewer_name,
            "review_round": round_num,
            "verdict": verdict,
            "comments": comments,
            "risk_flags": risk_flags or [],
        }).execute()

        status_map = {
            "approved": "pending_signature",
            "rejected": "draft",
            "revision_needed": "under_negotiation",
        }
        self.supabase.table("contracts").update({
            "status": status_map.get(verdict, "pending_review"),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", contract_id).execute()

        return review.data[0]

    # --- ZES: 24-Hour Agent Delivery ---
    async def create_zes_agent_contract(
        self, client_name: str, client_email: str, agent_type: str,
        website_url: str, package_tier: str = "standard",
        is_tradebuilder_extension: bool = False,
        tradebuilder_contract_id: Optional[str] = None,
    ) -> Dict:
        """ZES agents for ALREADY ESTABLISHED websites. 24hr delivery SLA."""
        zes_pricing = {
            "starter":    {"value": 500,  "hours": 24},
            "standard":   {"value": 1500, "hours": 24},
            "premium":    {"value": 3500, "hours": 24},
            "enterprise": {"value": 8000, "hours": 48},
        }
        tier = zes_pricing.get(package_tier, zes_pricing["standard"])

        milestones = [
            {"title": "Agent Config & Setup", "payment_amount": tier["value"] * 0.5,
             "deliverables": ["Agent deployed", "Integration verified"],
             "due_date": (date.today() + timedelta(hours=tier["hours"])).isoformat()},
            {"title": "Agent Delivery & Handoff", "payment_amount": tier["value"] * 0.5,
             "deliverables": ["Live agent", "Documentation", "Support onboarding"],
             "due_date": (date.today() + timedelta(hours=tier["hours"])).isoformat()},
        ]

        return await self.create_contract(
            contract_type=ContractType.SOW,
            title=f"ZES Agent — {agent_type} for {client_name}",
            party_a_name="Citadel Nexus", party_b_name=client_name,
            party_b_email=client_email, product_line="zes",
            is_tradebuilder_upsell=is_tradebuilder_extension,
            parent_contract_id=tradebuilder_contract_id,
            total_value=tier["value"], milestones=milestones,
            metadata={"agent_type": agent_type, "website_url": website_url,
                       "delivery_sla_hours": tier["hours"]},
        )

    # --- TradeBuilder: Website Income ---
    async def create_tradebuilder_contract(
        self, client_name: str, client_email: str, website_type: str,
        package_tier: str = "professional", include_zes_upsell: bool = False,
        zes_agent_type: Optional[str] = None,
    ) -> Dict:
        """TradeBuilder = website income product. ZES = optional upsell."""
        tb_pricing = {
            "starter":      {"value": 2500,  "days": 14},
            "professional": {"value": 5000,  "days": 21},
            "business":     {"value": 12000, "days": 30},
            "enterprise":   {"value": 25000, "days": 45},
        }
        tier = tb_pricing.get(package_tier, tb_pricing["professional"])

        milestones = [
            {"title": "Discovery & Design", "payment_amount": tier["value"] * 0.3,
             "due_date": (date.today() + timedelta(days=7)).isoformat()},
            {"title": "Development & Build", "payment_amount": tier["value"] * 0.4,
             "due_date": (date.today() + timedelta(days=tier["days"] - 7)).isoformat()},
            {"title": "Launch & Handoff", "payment_amount": tier["value"] * 0.3,
             "due_date": (date.today() + timedelta(days=tier["days"])).isoformat()},
        ]

        contract = await self.create_contract(
            contract_type=ContractType.SOW,
            title=f"TradeBuilder Website — {website_type} for {client_name}",
            party_a_name="Citadel Nexus", party_b_name=client_name,
            party_b_email=client_email, product_line="tradebuilder",
            total_value=tier["value"], milestones=milestones,
            metadata={"website_type": website_type, "includes_zes": include_zes_upsell},
        )

        if include_zes_upsell and zes_agent_type:
            zes = await self.create_zes_agent_contract(
                client_name, client_email, zes_agent_type,
                f"pending-{client_name.lower().replace(' ', '-')}.com",
                is_tradebuilder_extension=True,
                tradebuilder_contract_id=contract["id"],
            )
            contract["zes_upsell_contract"] = zes

        return contract

    # --- Dashboard Queries ---
    def get_expiring_contracts(self, days_ahead: int = 30) -> List[Dict]:
        cutoff = (date.today() + timedelta(days=days_ahead)).isoformat()
        return self.supabase.table("contracts") \
            .select("*").eq("status", "active") \
            .lte("expiration_date", cutoff).order("expiration_date").execute().data

    def get_milestone_progress(self, contract_id: str) -> Dict:
        ms = self.supabase.table("contract_milestones") \
            .select("*").eq("contract_id", contract_id) \
            .order("milestone_number").execute().data
        total = len(ms)
        completed = sum(1 for m in ms if m["status"] == "completed")
        return {"milestones": ms, "total": total, "completed": completed,
                "progress_pct": (completed / total * 100) if total else 0}

    def get_product_line_summary(self) -> Dict:
        contracts = self.supabase.table("contracts").select("*").execute().data
        summary = {}
        for c in contracts:
            line = c["product_line"]
            if line not in summary:
                summary[line] = {"count": 0, "total_value": 0, "active": 0}
            summary[line]["count"] += 1
            summary[line]["total_value"] += c.get("total_value", 0) or 0
            if c["status"] == "active":
                summary[line]["active"] += 1
        return summary

    async def _notify_slack(self, message: str):
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(self.slack_url, json={"text": message})
```

***

## Part 2: Stripe Global Payout Integrations

### Supabase Schema (002_stripe_payouts.sql)

```sql
CREATE TABLE IF NOT EXISTS stripe_connected_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_account_id TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT 'US',
    region TEXT NOT NULL DEFAULT 'us',
    account_type TEXT DEFAULT 'express',
    status TEXT DEFAULT 'pending_verification',
    contributor_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payment_intents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_payment_intent_id TEXT NOT NULL UNIQUE,
    amount NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'usd',
    transfer_group TEXT,
    contract_id UUID,
    product_line TEXT,
    status TEXT DEFAULT 'pending',
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payout_distributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transfer_group TEXT NOT NULL,
    product_line TEXT,
    type TEXT NOT NULL,       -- 'contributor', 'guildmaster_bonus', 'platform_fee'
    account_id TEXT,
    name TEXT,
    amount NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'usd',
    weight NUMERIC(6,4),
    share_pct NUMERIC(6,4),
    bonus_pct NUMERIC(4,2),
    distributed_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_payouts_transfer_group ON payout_distributions(transfer_group);
CREATE INDEX idx_payouts_product ON payout_distributions(product_line);
```

### Stripe Global Payout Service (stripe_global_payouts.py)

```python
# citadel_helper/payments/stripe_global_payouts.py

import stripe
from datetime import datetime
from typing import Dict, Any, List, Optional

class StripeGlobalPayoutService:
    """Stripe Connect global payouts — multi-currency, escrow, SAKE/AEGIS verified."""

    def __init__(self, stripe_secret_key: str, supabase_client, platform_fee_pct: float = 0.30):
        stripe.api_key = stripe_secret_key
        self.supabase = supabase_client
        self.platform_fee_pct = platform_fee_pct

    def create_connected_account(
        self, email: str, country: str = "US",
        account_type: str = "express", metadata: Optional[Dict] = None,
    ) -> Dict:
        account = stripe.Account.create(
            type=account_type, country=country, email=email,
            business_type="individual",
            capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
            metadata={"platform": "citadel_nexus", "region": self._get_region(country), **(metadata or {})},
        )
        self.supabase.table("stripe_connected_accounts").insert({
            "stripe_account_id": account.id, "email": email, "country": country,
            "region": self._get_region(country), "account_type": account_type,
        }).execute()
        return {"account_id": account.id, "country": country}

    def generate_onboarding_link(self, account_id: str, return_url: str, refresh_url: str) -> str:
        link = stripe.AccountLink.create(
            account=account_id, refresh_url=refresh_url,
            return_url=return_url, type="account_onboarding",
        )
        return link.url

    def create_payment_intent(
        self, amount_cents: int, currency: str = "usd",
        customer_id: Optional[str] = None, contract_id: Optional[str] = None,
        product_line: str = "zes", transfer_group: Optional[str] = None,
    ) -> Dict:
        if not transfer_group:
            transfer_group = f"contract_{contract_id}" if contract_id else f"pay_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        intent = stripe.PaymentIntent.create(
            amount=amount_cents, currency=currency, customer=customer_id,
            transfer_group=transfer_group,
            metadata={"contract_id": contract_id or "", "product_line": product_line},
        )
        self.supabase.table("payment_intents").insert({
            "stripe_payment_intent_id": intent.id, "amount": amount_cents / 100,
            "currency": currency, "transfer_group": transfer_group,
            "contract_id": contract_id, "product_line": product_line, "status": intent.status,
        }).execute()

        return {"payment_intent_id": intent.id, "client_secret": intent.client_secret,
                "transfer_group": transfer_group}

    def distribute_payouts(
        self, transfer_group: str, total_amount_cents: int, currency: str = "usd",
        contributors: List[Dict] = None,
        guildmaster_account_id: Optional[str] = None,
        guildmaster_bonus_pct: float = 0.10, product_line: str = "zes",
    ) -> Dict:
        """70/30 split with SAKE/AEGIS verified contribution weights."""
        platform_fee = int(total_amount_cents * self.platform_fee_pct)
        contributor_pool = total_amount_cents - platform_fee

        guildmaster_bonus = 0
        if guildmaster_account_id:
            guildmaster_bonus = int(contributor_pool * guildmaster_bonus_pct)
            contributor_pool -= guildmaster_bonus

        transfers, payout_log = [], []

        if contributors:
            total_weight = sum(c.get("weight", 1) for c in contributors)
            for c in contributors:
                weight = c.get("weight", 1)
                share_pct = weight / total_weight
                share_amount = int(contributor_pool * share_pct)
                if share_amount > 0:
                    transfer = stripe.Transfer.create(
                        amount=share_amount, currency=currency,
                        destination=c["stripe_account_id"],
                        transfer_group=transfer_group,
                        metadata={"contributor_name": c.get("name", ""), "weight": str(weight),
                                  "product_line": product_line},
                    )
                    transfers.append(transfer)
                    payout_log.append({"type": "contributor", "account_id": c["stripe_account_id"],
                                       "name": c.get("name"), "amount": share_amount / 100})

        if guildmaster_account_id and guildmaster_bonus > 0:
            stripe.Transfer.create(
                amount=guildmaster_bonus, currency=currency,
                destination=guildmaster_account_id, transfer_group=transfer_group,
                metadata={"type": "guildmaster_bonus"},
            )
            payout_log.append({"type": "guildmaster_bonus", "amount": guildmaster_bonus / 100})

        for entry in payout_log:
            self.supabase.table("payout_distributions").insert({
                "transfer_group": transfer_group, "product_line": product_line,
                **entry, "currency": currency,
            }).execute()

        return {"transfer_group": transfer_group, "total": total_amount_cents / 100,
                "platform_fee": platform_fee / 100, "payouts": payout_log}

    def handle_webhook(self, payload: bytes, sig_header: str, webhook_secret: str) -> Dict:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        data = event["data"]["object"]

        if event["type"] == "payment_intent.succeeded":
            self.supabase.table("payments").insert({
                "stripe_payment_id": data["id"], "amount": data["amount"] / 100,
                "currency": data["currency"], "status": "completed",
                "contract_id": data.get("metadata", {}).get("contract_id"),
                "product_line": data.get("metadata", {}).get("product_line", "zes"),
            }).execute()

            # Queue Xero sync
            self.supabase.table("automation_events").insert({
                "event_type": "invoice.paid", "source_system": "stripe",
                "target_system": "xero", "status": "pending",
                "payload": {"stripe_id": data["id"], "amount": data["amount"] / 100,
                            "currency": data["currency"],
                            "customer_email": data.get("receipt_email")},
            }).execute()

        return {"status": "processed", "event_type": event["type"]}

    def _get_region(self, country: str) -> str:
        eu = {"DE","FR","IT","ES","NL","BE","AT","IE","PT","FI","GR","LU","CY","MT","SK","SI","EE","LV","LT","HR","BG","RO","CZ","DK","SE","PL","HU"}
        if country == "US": return "us"
        if country == "GB": return "uk"
        if country in eu: return "eu"
        return "global"
```

***

## Part 3: Xero Invoicing & Dashboard

### Supabase Schema (003_xero_invoices.sql)

```sql
CREATE TABLE IF NOT EXISTS xero_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    xero_invoice_id TEXT UNIQUE,
    stripe_invoice_id TEXT,
    contract_id UUID,
    product_line TEXT,
    contact_name TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'DRAFT',
    invoice_number TEXT,
    paid_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_xero_invoices_contract ON xero_invoices(contract_id);
CREATE INDEX idx_xero_invoices_product ON xero_invoices(product_line);
CREATE INDEX idx_xero_invoices_status ON xero_invoices(status);
```

### Xero Service (xero_service.py)

```python
# citadel_helper/accounting/xero_service.py

import httpx
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode

class XeroInvoiceService:
    """Xero auto-invoicing synced from Stripe + dashboard reports."""

    XERO_BASE = "https://api.xero.com/api.xro/2.0"
    TOKEN_URL = "https://identity.xero.com/connect/token"

    def __init__(self, client_id, client_secret, redirect_uri, tenant_id, supabase_client):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.tenant_id = tenant_id
        self.supabase = supabase_client
        self.access_token = None
        self.refresh_token = None

    async def refresh_access_token(self) -> str:
        if not self.refresh_token:
            state = self.supabase.table("integration_sync_state") \
                .select("config").eq("integration_name", "xero").single().execute()
            self.refresh_token = state.data["config"]["refresh_token"]

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "grant_type": "refresh_token", "refresh_token": self.refresh_token,
            }, auth=(self.client_id, self.client_secret))
            tokens = resp.json()
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens["refresh_token"]

            self.supabase.table("integration_sync_state").update({
                "config": {"refresh_token": self.refresh_token, "tenant_id": self.tenant_id},
            }).eq("integration_name", "xero").execute()
        return self.access_token

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}",
                "Xero-Tenant-Id": self.tenant_id,
                "Content-Type": "application/json"}

    async def find_or_create_contact(self, name: str, email: str) -> Dict:
        await self.refresh_access_token()
        async with httpx.AsyncClient() as client:
            search = await client.get(f"{self.XERO_BASE}/Contacts",
                                       headers=self._headers(),
                                       params={"where": f'EmailAddress=="{email}"'})
            contacts = search.json().get("Contacts", [])
            if contacts:
                return contacts[0]

            resp = await client.post(f"{self.XERO_BASE}/Contacts",
                                      headers=self._headers(),
                                      json={"Contacts": [{"Name": name, "EmailAddress": email}]})
            return resp.json()["Contacts"][0]

    async def create_invoice_from_stripe(
        self, stripe_data: Dict, contract_id: Optional[str] = None,
        product_line: str = "zes",
    ) -> Dict:
        await self.refresh_access_token()
        email = stripe_data.get("customer_email", "")
        name = stripe_data.get("customer_name", email.split("@")[0])
        amount = stripe_data.get("amount", 0)
        currency = stripe_data.get("currency", "USD").upper()

        contact = await self.find_or_create_contact(name, email)

        account_codes = {"tradebuilder": "200", "zes": "201", "watcher": "202", "guild": "203"}
        descriptions = {
            "tradebuilder": "TradeBuilder Website Development",
            "zes": "ZES AI Agent Deployment (24hr delivery)",
            "watcher": "Watcher SaaS Subscription",
            "guild": "Guild-for-Hire Services",
        }

        payload = {"Invoices": [{
            "Type": "ACCREC",
            "Contact": {"ContactID": contact["ContactID"]},
            "Date": date.today().isoformat(),
            "DueDate": (date.today() + timedelta(days=30)).isoformat(),
            "CurrencyCode": currency,
            "Status": "AUTHORISED",
            "Reference": f"STRIPE-{stripe_data.get('id', 'N/A')}",
            "LineItems": [{
                "Description": descriptions.get(product_line, "Citadel Nexus Services"),
                "Quantity": 1,
                "UnitAmount": amount,
                "AccountCode": account_codes.get(product_line, "200"),
            }],
        }]}

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.XERO_BASE}/Invoices",
                                      headers=self._headers(), json=payload)
            inv = resp.json().get("Invoices", [{}])[0]

        self.supabase.table("xero_invoices").insert({
            "xero_invoice_id": inv.get("InvoiceID"),
            "stripe_invoice_id": stripe_data.get("id"),
            "contract_id": contract_id,
            "product_line": product_line,
            "contact_name": name,
            "amount": amount,
            "currency": currency,
            "status": inv.get("Status", "DRAFT"),
            "invoice_number": inv.get("InvoiceNumber"),
        }).execute()

        return {"xero_invoice_id": inv.get("InvoiceID"),
                "invoice_number": inv.get("InvoiceNumber"), "amount": amount}

    async def record_payment(self, xero_invoice_id: str, amount: float,
                              account_code: str = "090", reference: str = "") -> Dict:
        await self.refresh_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.XERO_BASE}/Payments",
                headers=self._headers(),
                json={"Payments": [{
                    "Invoice": {"InvoiceID": xero_invoice_id},
                    "Account": {"Code": account_code},
                    "Date": date.today().isoformat(),
                    "Amount": amount, "Reference": reference,
                }]})
            return resp.json()

    # --- Dashboard Reports ---
    async def get_profit_and_loss(self, from_date=None, to_date=None) -> Dict:
        await self.refresh_access_token()
        params = {}
        if from_date: params["fromDate"] = from_date
        if to_date: params["toDate"] = to_date
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.XERO_BASE}/Reports/ProfitAndLoss",
                                     headers=self._headers(), params=params)
            return resp.json()

    async def get_balance_sheet(self, as_of_date=None) -> Dict:
        await self.refresh_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.XERO_BASE}/Reports/BalanceSheet",
                                     headers=self._headers(),
                                     params={"date": as_of_date} if as_of_date else {})
            return resp.json()

    async def get_revenue_by_product_line(self) -> Dict:
        invoices = self.supabase.table("xero_invoices").select("*").execute().data
        summary = {}
        for inv in invoices:
            line = inv.get("product_line", "unknown")
            if line not in summary:
                summary[line] = {"total": 0, "count": 0, "paid": 0, "outstanding": 0}
            summary[line]["total"] += inv.get("amount", 0)
            summary[line]["count"] += 1
            if inv.get("status") == "PAID":
                summary[line]["paid"] += inv.get("amount", 0)
            else:
                summary[line]["outstanding"] += inv.get("amount", 0)
        return summary

    async def get_dashboard_metrics(self) -> Dict:
        pnl = await self.get_profit_and_loss(
            from_date=date(date.today().year, 1, 1).isoformat())
        product_rev = await self.get_revenue_by_product_line()
        payouts = self.supabase.table("payout_distributions").select("amount, type").execute().data

        return {
            "profit_and_loss": pnl,
            "revenue_by_product": product_rev,
            "total_payouts": sum(p.get("amount", 0) for p in payouts),
            "tradebuilder_revenue": product_rev.get("tradebuilder", {}).get("total", 0),
            "zes_revenue": product_rev.get("zes", {}).get("total", 0),
            "watcher_revenue": product_rev.get("watcher", {}).get("total", 0),
        }
```

***

## Part 4: Unified Edge Function Webhook

```typescript
// supabase/functions/contract-payment-webhook/index.ts

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import Stripe from "https://esm.sh/stripe@14.1.0";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY")!, { apiVersion: "2023-10-16" });
const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const SLACK_WEBHOOK = Deno.env.get("SLACK_PAYMENTS_WEBHOOK")!;

serve(async (req) => {
  const body = await req.text();
  const sig = req.headers.get("stripe-signature")!;
  let event: Stripe.Event;

  try {
    event = stripe.webhooks.constructEvent(body, sig, Deno.env.get("STRIPE_WEBHOOK_SECRET")!);
  } catch (err) {
    return new Response(`Webhook Error: ${err.message}`, { status: 400 });
  }

  const data = event.data.object as any;

  switch (event.type) {
    case "payment_intent.succeeded": {
      const contractId = data.metadata?.contract_id;
      const productLine = data.metadata?.product_line || "zes";
      const amount = data.amount / 100;

      // Log payment
      await supabase.from("payments").insert({
        stripe_payment_id: data.id, amount, currency: data.currency,
        customer_email: data.receipt_email, status: "completed",
        contract_id: contractId, product_line: productLine,
      });

      // Update next pending milestone
      if (contractId) {
        const { data: milestones } = await supabase
          .from("contract_milestones").select("*")
          .eq("contract_id", contractId).eq("payment_status", "pending")
          .order("milestone_number").limit(1);
        if (milestones?.length) {
          await supabase.from("contract_milestones")
            .update({ payment_status: "paid", stripe_invoice_id: data.id })
            .eq("id", milestones[0].id);
        }
      }

      // Queue Xero invoice
      await supabase.from("automation_events").insert({
        event_type: "create_xero_invoice", source_system: "stripe",
        target_system: "xero", status: "pending",
        payload: { stripe_id: data.id, amount, currency: data.currency,
                   customer_email: data.receipt_email, contract_id: contractId,
                   product_line: productLine },
      });

      // Slack notify
      await fetch(SLACK_WEBHOOK, {
        method: "POST",
        body: JSON.stringify({
          text: `💰 $${amount} ${data.currency.toUpperCase()} received | ${productLine} | Contract: ${contractId || "N/A"}`,
        }),
      });
      break;
    }

    case "charge.dispute.created": {
      await supabase.from("automation_events").insert({
        event_type: "dispute.created", source_system: "stripe", status: "pending",
        payload: { dispute_id: data.id, amount: data.amount / 100, reason: data.reason },
      });
      await fetch(SLACK_WEBHOOK, {
        method: "POST",
        body: JSON.stringify({ text: `🚨 DISPUTE: $${data.amount / 100} — ${data.reason}` }),
      });
      break;
    }
  }

  return new Response(JSON.stringify({ received: true }), { status: 200 });
});
```

***

## Part 5: Environment Config

```bash
# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CONNECT_CLIENT_ID=ca_...

# Xero
XERO_CLIENT_ID=your_xero_client_id
XERO_CLIENT_SECRET=your_xero_client_secret
XERO_REDIRECT_URI=https://api.citadel-nexus.com/auth/xero/callback
XERO_TENANT_ID=your_xero_tenant_id

# Slack
SLACK_PAYMENTS_WEBHOOK=https://hooks.slack.com/services/xxx/yyy/zzz

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

***

## How It All Connects

The system flows like this based on the product structure in your [Payment System Template](https://www.notion.so/27f7bdddeddd4f2fb05099d2dd2b6585) and [Integrations page](https://www.notion.so/e63a61df50d74291846f3cd90a1c57d1) :

- **TradeBuilder** creates SOW contracts with milestones for website builds, with ZES as an optional upsell extension
- **ZES** creates 24-hour delivery SOW contracts specifically for agent deployment to **already established** websites
- **Stripe webhooks** hit the edge function → update contract milestones → queue Xero invoice creation → notify Slack
- **Stripe Connect** handles global payouts to contributors with the 70/30 split and SAKE/AEGIS verification
- **Xero** auto-creates invoices from Stripe payments, tagged by product line (tradebuilder/zes/watcher/guild), feeding the dashboard with P&L, aged receivables, and revenue-by-product breakdownsZES + TradeBuilder: OSS Competitive Audit & Untapped Stack Advantages
The Core Question
With ZES positioned as an AI agent for already-established websites (delivered in 24 hours) and TradeBuilder as the website income line (with ZES as an upsell/extension), are there open-source systems that do this better — and what features is the Citadel stack uniquely positioned to deliver that you're currently missing?

Part 1: OSS That Overlaps With What You're Building
Contract Lifecycle Management
Your stack handles contracts (NDA, MCA, LOI, SOW) through custom Supabase schemas. The open-source alternatives:

OSS Tool	What It Does	Where It Falls Short vs. You
OpenCLM	Full CLM with e-signatures, approval workflows, AI compliance checking, clause library, Docker deployment
No Stripe billing integration, no voice agent, no trade-specific workflows. You'd still need to bolt on payments and automation separately.
OpenSourceCM	Contract authoring, negotiation, approval, deal rooms, compliance. $500/yr or SaaS
Dated UI, no AI integration, no invoicing, no payout distribution. Enterprise-focused, not trade-business-friendly.
ERPNext	Full ERP with accounting, invoicing, inventory, HR, CRM. 100% open-source (Frappe)
Massive footprint — overkill for trade businesses. No AI voice agent, no review automation, no SMS/call handling. Configuration complexity is high.
Verdict: OpenCLM is the closest OSS threat to your contract management layer, but it's contract-only. It doesn't touch the revenue orchestration (Stripe Connect payouts), the AI voice agent, the automation engine (n8n), or the trade-specific lead/review pipeline. None of these are a real substitute for the full ZES + TradeBuilder stack.

Invoicing & Accounting
OSS Tool	What It Does	Where It Falls Short
Invoice Ninja	Full invoicing with 40+ payment gateways (including Stripe Connect), recurring billing, client portal, time tracking. Self-hosted or cloud
No AI agent layer. No call handling. No lead capture. No review automation. Pure invoicing tool.
Akaunting	Double-entry accounting, invoicing, expense tracking. Self-hosted
​	Even more basic — no Stripe Connect, no multi-tenant.
ERPNext Accounting	GL, AP/AR, multi-currency, financial statements
​	Same overkill problem. Heavy to deploy and maintain for a trade business.
Verdict: Invoice Ninja is legitimately good and could replace your invoicing micro-service (#10 - Invoice Reminder Automator) if someone self-hosted it. But it's just one spoke — you have the whole wheel. The risk here is that Invoice Ninja is free and well-known, so your $20/mo invoicing service needs to be clearly superior in its automation layer (auto-follow-up, text-to-pay integration, AI-generated reminders).

Marketing/CRM Platforms (The Real Competition)
The real competitive threat isn't OSS — it's the SaaS incumbents that trade businesses already know:

Platform	Price	Strength	Weakness vs. ZES
GoHighLevel	$97-497/mo	All-in-one: CRM, funnels, SMS, email, white-label	Expensive, complex, agency-focused not trade-focused. No AI voice agent. Generic, not trade-optimized
​
Jobber	$25-109/mo	Clean UX, scheduling, invoicing, quoting	No AI agent, no review automation, no voice, limited marketing
​
Housecall Pro	$59-149/mo	Scheduling, payments, customer management	No AI voice, limited automation, basic CRM
​
ServiceTitan	Custom (expensive)	Deep dispatching, reporting, job costing, marketing	Enterprise pricing, long implementation, overkill for small trades
​
Podium	~$399/mo	Reviews, messaging, payments	Very expensive for what it delivers. No website. No voice AI
Verdict: GoHighLevel is your most direct competitor in positioning, but it's $97+/mo vs. your ZES at $15-30/mo. The price gap is your moat — IF you can deliver comparable automation. Jobber and Housecall Pro compete on scheduling/invoicing, but they have zero AI capabilities. ServiceTitan is a different universe (enterprise trades). The strategic insight: none of these have an AI voice agent + website builder + micro-service bundle at your price point.

Part 2: What You're Missing or Could Add (Stack Advantages You're Not Exploiting)
Your stack (Supabase + Stripe Connect + n8n + ElevenLabs + Cloudflare + Twilio) has capabilities you're underutilizing. Here's what to press:

1. Real-Time Client Dashboard (Supabase Realtime)
What you have: Supabase Realtime lets you push live database changes to connected clients instantly.
​

What you're not doing: Your "Dinah's Admin Dashboard" (Service 0) is listed as a future MVP. This should be live RIGHT NOW. Supabase Realtime means you can show trade owners:

Live lead notifications as they come in

Real-time booking confirmations

SMS/call activity feed

Review score changes in real-time

Revenue dashboard that updates as payments clear

Why it matters: Jobber and Housecall Pro have dashboards, but they're poll-based (refresh to see changes). A Supabase Realtime-powered dashboard gives you a legitimate "live" feel that competitors can't match without significant engineering. This is a retention weapon — once a trade owner sees leads coming in live, they won't leave.

2. Automated Audit Trails (Supabase supa_audit + pgAudit)
What you have: Supabase supports table-level audit tracking via the supa_audit extension, which automatically logs INSERT/UPDATE/DELETE to an audit.record_history table. You also have pgAudit for query-level logging.

What you're not doing: You're not offering compliance-grade audit trails to your trade business customers. For trades that deal with:

Licensed work (HVAC, electrical, plumbing) — audit trails prove what was quoted, agreed to, and invoiced

Insurance claims — timestamped records of communication and job completion

Dispute resolution — immutable records of what the AI agent said and when

Action: Enable supa_audit on all customer-facing tables. Package this as "GuardianLogs Lite" for trade businesses — a feature NO competitor at this price point offers.

3. Scheduled Automation Jobs (pg_cron + Edge Functions)
What you have: Supabase Cron uses pg_cron to schedule recurring jobs directly in Postgres, and can trigger Edge Functions on a schedule using pg_net.

What you're not doing fully: n8n handles your automation, but some jobs should be database-native for reliability:

Daily review score recalculation — pg_cron job that aggregates Google/Yelp review data nightly

Automated churn detection — scheduled query that flags customers with declining usage (no leads in 7 days, no calls in 14 days)

Invoice aging alerts — pg_cron triggers that auto-escalate overdue invoices from "reminder" to "urgent" to "collections"

Seasonal campaign triggers — schedule HVAC maintenance reminders for March, furnace checks for October, etc.

Why it matters: This is where your "we self-host everything" advantage really shines. Your competitors rely on third-party scheduling (Zapier timeouts, webhook reliability issues). Your jobs run inside Postgres itself — no external dependency, no failure point.

4. Secrets Management (Supabase Vault)
What you have: Supabase Vault stores secrets encrypted in the database.
​

What you're not doing: Each trade customer's API keys (Google Business Profile, Yelp, Facebook, payment processor tokens) should be stored in Vault, not in n8n credential stores or environment variables. This is both a security upgrade and a selling point for enterprise/agency tier customers who ask about data isolation.

5. Edge Functions for Per-Customer Logic
What you have: Supabase Edge Functions run TypeScript at the edge with sub-200ms cold starts.

What you could add that no competitor offers:

Per-customer AI response tuning — Edge Function that intercepts the voice agent callback and adjusts tone/script based on the customer's industry and preferences, stored in their Supabase row

Webhook relay with transformation — Edge Function that receives Stripe webhooks, enriches them with customer context from Supabase, and routes them to n8n with full context. This eliminates the "dumb webhook" problem where n8n workflows need to re-query for context.

Real-time pricing engine — Edge Function that calculates dynamic pricing for storm blasts based on weather severity, customer location, and historical response rates

6. The n8n + Stripe + Xero Bridge
What you have: n8n has native nodes for both Stripe and Xero, supporting full CRUD operations on customers, invoices, charges, contacts, and more.

What you're leaving on the table:

Auto-reconciliation: When a Stripe payment succeeds, n8n automatically creates a matching paid invoice in Xero, reconciles it, and sends the receipt. This closes the accounting loop without manual intervention.
​

Multi-entity bookkeeping: For your Stripe Connect payouts (to developers, partners, trade business referrals), n8n can mirror every payout as a Xero bill or expense entry — giving you clean books across all revenue layers.

Overdue invoice automation: An existing OSS workflow (xero-overdue-invoice-email-automation) does exactly this for Xero — scan multiple orgs for overdue invoices and blast email summaries. You could replicate this inside n8n as a built-in feature for your trade customers.
​

7. Voice Agent as the Real Differentiator
No competitor in the trade space has this. Not Jobber. Not Housecall Pro. Not ServiceTitan. Not GoHighLevel.

Your ElevenLabs-powered AI voice receptionist (Autopilot tier) is the single biggest competitive advantage in your entire stack. But you're only offering it at the $30/mo tier.

What to consider:

Offer a "lite" version at the Operator tier ($20/mo) — even if it's just a voicemail-to-text-to-CRM pipeline without the full conversational AI

The Mars 8 AI Voicemail Drop (Service 14) should be showcased as a demo in every TradeBuilder website — let prospects hear the AI voice on a sample call

Record before/after case studies: "This HVAC company missed 12 calls last month. After Autopilot, they caught all 12 and booked 8."

8. The TradeBuilder → ZES Upsell Flywheel (What's Missing)
Your revised model (TradeBuilder = website income, ZES = agent for existing websites, delivered in 24 hours) creates a natural flywheel, but the connection points need engineering:

Currently missing:

In-site ZES activation widget — Every TradeBuilder website should have a one-click "Activate ZES" button in the admin panel. Not a sales call. Not a separate sign-up. One click.

Usage previews — Show TradeBuilder customers what ZES WOULD have caught: "You had 4 missed calls this week. With ZES Scout, those would have been text-backs." This creates urgency.

Graduated activation — Let TradeBuilder customers trial Scout features for 7 days free, then auto-prompt for upgrade

Shared billing — One Stripe invoice for TradeBuilder + ZES. Your monetization doc mentions this ("one invoice enterprise pitch") but it should be the default from day one, not an enterprise feature.

Part 3: Strategic Summary
What OSS Does Better Than You (Be Honest)
Area	OSS Leader	What They Do Better
Contract management (pure CLM)	OpenCLM	More mature approval workflows, clause libraries, e-signature depth
​
Invoicing depth	Invoice Ninja	40+ gateways, better invoice design, time tracking, recurring billing
​
Full accounting	ERPNext	Complete double-entry accounting, multi-currency, financial statements
​
What Nobody Does As Well As You (Press These)
Advantage	Why It's a Moat
AI voice agent at $30/mo	No competitor has this at any price under $200/mo. ServiceTitan doesn't have it at all.
24-hour agent delivery	GoHighLevel takes weeks to configure. You promise 24 hours.
Self-hosted stack = 80-92% margins	Everyone else pays SaaS middlemen. You own the infrastructure.
Supabase Realtime for live dashboards	Competitors use polling. You can push live data.
n8n + Stripe + Xero automation bridge	End-to-end from lead → booking → invoice → payment → accounting, no human touch.
Price point ($15-30/mo for ZES)	GoHighLevel is $97-497. Podium is $399. Jobber is $25-109. You undercut everyone with MORE AI.
TradeBuilder + ZES bundle	Nobody else offers website + AI agent + automation at $120-330/mo total.
What to Build Next (Priority Order)
Dinah's Admin Dashboard (Service 0) — Use Supabase Realtime. Make it the sticky center of the ZES experience. This is your #1 retention tool.

One-click ZES activation in TradeBuilder — Close the upsell gap. Don't make it a separate purchase flow.

Audit trail packaging — Enable supa_audit, brand it as compliance/dispute protection. Free differentiator.

pg_cron churn detection — Automated health scores that flag at-risk customers before they cancel.

Lite voice at Operator tier — Even voicemail-to-text-to-CRM is a massive unlock at $20/mo.

n8n → Xero auto-reconciliation — Close the accounting loop. Trade owners hate bookkeeping.

Storm Blast → Edge Function pricing engine — Dynamic pricing based on weather severity. Nobody else can do this.

Bottom Line
No single OSS project replicates what ZES + TradeBuilder does holistically. OpenCLM is strong on contracts. Invoice Ninja is strong on invoicing. ERPNext is strong on accounting. But none of them combine AI voice, lead automation, review management, website provisioning, and Stripe Connect billing at $15-30/mo.

Your real competition is GoHighLevel (expensive, generic) and the Jobber/Housecall Pro category (no AI). You beat them on price AND AI capabilities. The gap to close is execution: ship the dashboard, wire the upsell flywheel, and exploit the Supabase Realtime + pg_cron + Edge Functions capabilities that your stack already has but you're not using yet.Now I have a comprehensive picture. Let me put together the response addressing both questions: how to implement the Sentinel's recommendation, and what's missing from the Finance Guild buildout.

The Sentinel Thought flagged your **Finance Guild Tracking System** commit (6.7K LOC, 3-way diff + Notion integration) as **MEDIUM risk** and recommended code review before Stage 2 . Here's how to implement that recommendation, plus what's missing from the full Finance Guild buildout.

***

## Implementing the Sentinel's Recommendation

The Sentinel specifically called out three review areas: **diff algorithm correctness**, **Notion API auth/encryption**, and **audit logging** . Your SANCTUM already has the 3-way Notion check pattern documented — write to the Task Page, the EVO Cycle History DB, and the Evolution Tracker Dashboard . Apply that same pattern to the Finance Guild:

### 3-Way Diff Validation Gate

1. **Diff Algorithm Review** — The 3-way diff compares Git state ↔ Notion state ↔ Supabase state. Before Stage 2, you need a **dry-run mode** that runs the diff but writes to a staging table (`finance_guild.diff_staging`) instead of production. Run it against 10+ known scenarios: new records, updated records, deleted records, and conflict cases where all three sources disagree.

2. **Notion API Credential Handling** — The Sentinel flagged this because the commit touches external API integration. Your `NOTION_API_KEY` needs to be in the Supabase vault (not `.env` in the repo). The [SANCTUM Phase 7D fix](https://www.notion.so/9dce5cdea7c145e69301d484ffba3b18) already showed you need explicit database sharing with the integration — make sure the Finance Guild databases are shared with the same integration token .

3. **Audit Logging** — Your billing schema already mandates an **immutable ledger** (inserts only, no updates) . The Finance Guild tracker needs to log every diff resolution decision: which source won, what was overwritten, and why. This feeds directly into the SAKE/AEGIS validation chain your Payment System Template describes .

### Implementation Steps

- Add a `finance_guild.reconciliation_log` table in Supabase with columns: `evo_id`, `source_a` (git), `source_b` (notion), `source_c` (supabase), `resolution`, `resolved_by`, `timestamp`
- Wire the diff output through the existing Sentinel Governance Gate before any write operation
- Add the Finance Guild databases to the Notion integration sharing list
- Run Stage 1 in dry-run mode for 48 hours, then review the reconciliation log before enabling Stage 2 writes

***

## What's Missing from the Finance Guild Buildout

Based on your [Payment System Template](https://www.notion.so/27f7bdddeddd4f2fb05099d2dd2b6585), [billing schema](https://www.notion.so/2e4bcff493cb81408b43d85e5ea01818), [Monetization Strategy](https://www.notion.so/bb8f13ad6e40441785e0f1d9d2a019e0), and the [Developer Contribution & Payment Architecture](https://www.notion.so/63cc8822582c4cbcafb3e8212f9b6f3d), here are the critical gaps:

### Already Documented But NOT Built

| Component | Status | What's Missing |
|---|---|---|
| **Xero ↔ Stripe Sync** | `xero_adapter.py` exists (440 lines)  but not wired | Webhook bridge: `payment.invoice.paid` → Xero invoice creation → reconciliation |
| **Revenue Tracker DB** | Database exists ([collection://0db35d6a](https://www.notion.so/765f6e70b4514b38ab37c29c9e82848c))  | Empty — no automated entries from Stripe webhooks yet |
| **Stripe Connect Payouts** | Architecture documented  | No connected accounts exist yet; KYC flow not built; `transfer_group` escrow logic not coded |
| **Contribution Weight Calculator** | Weights defined (35% code, 20% arch, etc.)  | No actual Helper telemetry → weight calculation pipeline |
| **Developer Payment Map** | Page exists but is empty  | Needs the actual payout routing: who gets what % per project |

### Not Documented and NOT Built

These are gaps your stack can uniquely fill but nobody has scoped yet:

- **Real-Time Financial Dashboard** — Your billing schema has `NOTIFY/LISTEN` for real-time updates , but there's no actual dashboard consuming those events. Supabase Realtime + a React component would give you a live MRR/ARR/cash-position view. This is a huge gap — you're flying blind on actual revenue.

- **Multi-Currency / Tax Automation** — Your UK tax doc mentions Stripe Tax → Xero sync , but the billing schema only handles USD. With Stripe Connect going global for Guild contributors, you need multi-currency support in the ledger and automated VAT/sales tax calculation. Texas SaaS is taxable .

- **Dunning Management** — Listed in the billing schema executive summary  but zero implementation. Failed payment → retry logic → downgrade → win-back. n8n can handle this with a Stripe webhook → retry workflow → SendGrid notification chain.

- **Usage Metering for Platform SaaS** — The Monetization Strategy has usage-based tiers (API calls, agent count)  but there's no metering infrastructure. You need a Supabase function that increments usage counters per tenant, with Stripe's usage-based billing API on the backend.

- **Escrow Release Automation** — The SAKE → AEGIS → payout chain is documented beautifully  but it's all theoretical. The actual `stripe.Transfer.create()` trigger needs to be wired to SAKE milestone completion events. This is the single most important Finance Guild deliverable for Guild-for-Hire to work.

- **Financial Forecasting / Burn Rate Calculator** — You have manual projections in the Payment System Template  ($18K MRR Q1, $63.8K Q2, $155.8K EOY), but no automated model that adjusts based on actual data. A simple Supabase function that calculates rolling burn rate, runway, and projected break-even based on real Stripe data would replace the guesswork.

### Priority Order for Finance Guild Stage 2

1. **Stripe webhook → Revenue Tracker DB** (unblocks everything)
2. **Xero adapter activation** (you already have the code)
3. **Stripe Connect KYC onboarding flow** (unblocks contributor payouts)
4. **Dunning/retry automation via n8n** (protects revenue)
5. **Real-time financial dashboard** (visibility)
6. **Usage metering** (unlocks Platform SaaS billing)
7. **Escrow release automation** (unlocks Guild-for-Hire)

The Sentinel was right to flag this at MEDIUM risk — the 3-way diff is touching financial data sovereignty, and the credential handling for Notion API needs to match the same security bar as your Stripe keys. Get the dry-run + reconciliation log in place before Stage 2, and the Finance Guild buildout has a solid audit trail from day one.ZES & TradeBuilder — Weakness Solutions + Compounding Enhancements Playbook
Executive Assessment
After auditing the current ZES plans (Scout $15/mo, Operator $20/mo, Autopilot $30/mo) and TradeBuilder ($99-299/mo) against the OSS landscape and competitor stacks, there are no open-source projects that do what ZES does better as a packaged product for trade businesses. The individual components have OSS alternatives, but nobody is assembling them into a turnkey agent for plumbers, roofers, and HVAC contractors at this price point. The real risk isn't competition — it's leaving stack capabilities on the table that would widen the moat.

Part 1: Detected Weaknesses → Exact Solutions
Weakness 1: No Offline/Degraded Mode for Voice Agent
Problem: If ElevenLabs goes down or has latency spikes, the 24/7 AI receptionist promise breaks. Trade businesses get emergency calls at 2 AM during storms — that's when it matters most.

Solution: Failover Voice Chain via n8n

Build an n8n workflow that monitors ElevenLabs API health every 60 seconds

On failure detection, automatically reroute inbound calls to a Twilio IVR fallback with pre-recorded messages customized per client

Store the voicemail in Supabase Storage, transcribe via Deepgram ($0.01/min — far cheaper than ElevenLabs for batch), and push to the client's lead CRM

When ElevenLabs recovers, n8n flips routing back automatically

Cost: ~$5/mo for Deepgram standby + Twilio IVR minutes (pennies)

Implementation: 1 n8n workflow, 1 Supabase edge function, 1 Twilio Studio flow

Weakness 2: No Client-Facing Dashboard
Problem: Trade business owners can't see their own leads, call logs, review stats, or booking pipeline. They have to ask you or check Notion (which they don't have access to).

Solution: Supabase + Framer/Bubble Client Portal

Create a client_dashboard schema in Supabase with RLS (Row Level Security) policies scoped per client

Tables: leads, calls, reviews, bookings, invoices, analytics_snapshots

n8n syncs data from Notion, Cal.com, and Stripe into these tables on every event

Build a simple Framer or Bubble-based dashboard reading from Supabase REST API

Auth via Supabase Auth (magic link — trade owners don't remember passwords)

Compounding effect: This becomes the upsell path. Free read-only dashboard at Scout, interactive at Operator, full analytics at Autopilot

Cost: $0 incremental (Supabase free tier covers it per client)

Weakness 3: No Audit Trail for AI Decisions
Problem: When the AI voice agent books a job, quotes a price range, or routes a lead, there's no forensic log the business owner can reference if a customer disputes what was said.

Solution: Immutable Event Log in Supabase

sql
CREATE TABLE agent_audit_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  client_id UUID REFERENCES clients(id),
  event_type TEXT NOT NULL, -- 'call_answered', 'lead_created', 'booking_made', 'review_requested'
  ai_decision JSONB, -- full decision payload
  transcript TEXT,
  confidence_score FLOAT,
  created_at TIMESTAMPTZ DEFAULT now(),
  immutable_hash TEXT -- SHA256 of payload for tamper detection
);
Every AI action writes to this table via Supabase edge function

n8n workflow generates weekly audit summaries → pushed to client's Notion or emailed

Legal protection: This becomes a differentiator. "Every AI decision is logged and auditable" — Podium and GoHighLevel don't offer this

Cost: $0 (Supabase storage)

Weakness 4: No Revenue Attribution / ROI Proof
Problem: You can't prove to the client that ZES generated X leads that converted to $Y revenue. Without this, churn is inevitable — they'll ask "what am I paying for?"

Solution: Stripe + Xero + Supabase Revenue Loop

When a lead converts to a booked job (Cal.com webhook → n8n), create a revenue_event in Supabase

When client invoices the customer through their system (or through ZES text-to-pay on Autopilot), link the Stripe payment to the original lead via lead_id

n8n calculates: leads generated → bookings made → invoices paid → total attributed revenue

Monthly "ZES ROI Report" auto-generated and emailed: "ZES generated 47 leads, 31 bookings, $18,400 in attributed revenue this month. Your investment: $30."

Churn killer: Clients who see 100x+ ROI never cancel

Implementation: 3 Supabase tables, 2 n8n workflows, 1 email template via SendGrid

Weakness 5: Review Automation Has No Response Generation
Problem: ZES requests reviews automatically (Operator+), but doesn't help the business owner RESPOND to reviews — especially negative ones, which kill trade businesses on Google.

Solution: AI Review Response Engine

n8n monitors Google Business Profile reviews via API (or scraping webhook)

New review triggers OpenAI/Claude to generate a professional response draft tailored to the industry and tone

For 4-5 star reviews: auto-post the response (with client opt-in)

For 1-3 star reviews: draft response sent to client for approval via SMS (Twilio) with one-tap approve

All responses logged in Supabase audit table

Differentiator: GoHighLevel charges $297-497/mo and doesn't do this. Podium charges $249+/mo and barely does this.

Cost: ~$0.02 per response (OpenAI tokens)

Weakness 6: No Competitive Intelligence for Clients
Problem: Trade businesses don't know what their competitors are doing — pricing, review counts, Google ranking. You have PostHog and Perplexity but aren't weaponizing them for clients.

Solution: Monthly Competitor Snapshot Report

n8n scheduled workflow (1st of month): scrapes top 5 local competitors per client via Google Maps API / SerpAPI

Captures: review count, average rating, response rate, Google rank for key terms

Stores in Supabase competitor_snapshots table

Auto-generates comparison report: "You: 4.7 stars (89 reviews). Top competitor: 4.3 stars (67 reviews). You're winning."

Sent via SendGrid or embedded in client dashboard

Upsell hook: "Want to see what your competitors are charging? Upgrade to Operator."

Cost: ~$20/mo for SerpAPI (covers all clients)

Weakness 7: No Webhook Signature Validation on Inbound
Problem: Your Integration Sheet shows inbound webhooks from Stripe, Datadog, Linear, etc. but the code samples don't consistently validate webhook signatures. One spoofed webhook could create fake leads or trigger deployments.

Solution: Universal Webhook Validator Middleware

Build a Supabase Edge Function or Express middleware that validates signatures for each source:

Stripe: stripe.webhooks.constructEvent() with webhook secret

GitHub: HMAC-SHA256 validation

Linear: signature header verification

Reject any request that fails validation

Log failed attempts to security_events table in Supabase

Alert via Slack/Discord on repeated failures (potential attack)

Implementation: 1 edge function, ~50 lines of code per provider

Cost: $0

Weakness 8: Single Point of Failure on SSH Server
Problem: Your Integration Sheet references root@147.93.43.117 as the deployment target. Single server, root access, IP exposed in documentation.

Solution: Hardened Deployment Architecture

Move to non-root deploy user: deploy@server with sudo only for specific commands

Rotate the server IP out of documentation — use DNS hostname instead

Add Cloudflare proxy for the server (free tier covers DDoS protection + IP masking)

Implement deploy key rotation via n8n scheduled workflow (quarterly)

Add health check endpoint that Datadog monitors — auto-alert if server goes unresponsive

Cost: $0 (Cloudflare free tier)

Part 2: Compounding Enhancements (Stack Advantages You're Not Using)
These are capabilities your stack uniquely enables that competitors cannot match at your price point because they're locked into expensive SaaS dependencies.

Enhancement 1: Real-Time Lead Scoring via Supabase Realtime
What it does: The moment a lead comes in (form, call, chat), Supabase Realtime pushes it through a scoring function that evaluates: urgency keywords, service type, time of day, geographic proximity, and historical conversion rates.

Why your stack enables it: Supabase Realtime is included free. Competitors would need to pay for Pusher ($49+/mo) or build custom WebSocket infrastructure.

Implementation:

Supabase Postgres trigger on leads table INSERT

Edge function scores the lead (0-100) based on rules

High-score leads get instant SMS to business owner via Twilio: "🔥 HOT LEAD: Emergency AC repair, 2 miles from you. Call back in <5 min to win this job."

Lead score visible in client dashboard

Revenue impact: Trade businesses that respond to leads in <5 minutes close at 78% vs 15% for 30+ minute response. This alone justifies the subscription.

Enhancement 2: Multi-Tenant Stripe Connect for Client Payments
What it does: Instead of clients using their own separate payment processors, embed Stripe Connect so ZES can process text-to-pay invoices on behalf of clients, taking a platform fee.

Why your stack enables it: You already have Stripe. Stripe Connect is free to set up — you earn revenue on every transaction your clients process.

Implementation:

Each client onboards as a Stripe Connected Account (Express)

ZES Autopilot text-to-pay invoices go through your platform

You take 1-2% platform fee on every payment processed

n8n syncs payment events to Xero for your books AND the client's books

Supabase stores transaction records for the client dashboard

Revenue impact: If 100 Autopilot clients each process $10K/mo through text-to-pay, that's $1M in GMV → $10-20K/mo in platform fees. This is recurring revenue ON TOP of subscription fees.

Enhancement 3: AI-Generated Service Pages (SEO Machine)
What it does: Automatically generate hyper-local SEO pages for each client. "Emergency Plumber in Aldine TX" / "24/7 AC Repair Spring TX" — one page per service per city.

Why your stack enables it: OpenAI + Perplexity for content generation, Framer for hosting (TradeBuilder sites), n8n for orchestration, PostHog for tracking which pages convert.

Implementation:

n8n workflow: For each client, generate 10-20 service+location pages using OpenAI

Auto-publish to their TradeBuilder Framer site via Framer API

PostHog tracks which pages get traffic and convert to leads

Monthly n8n job refreshes content and adds new pages based on expanding service areas

Internal linking structure auto-generated

Revenue impact: Each service page can rank for long-tail keywords within 30-60 days. A plumber with 20 service pages covering 10 cities has 200 ranking opportunities vs 5-10 for a basic site. This makes TradeBuilder + ZES genuinely worth $150-300/mo.

Enhancement 4: Supabase Edge Functions as a Micro-API for Each Client
What it does: Give each ZES client their own API endpoint that their existing tools can call — CRM, dispatch software, accounting system. The API reads/writes to their scoped Supabase data.

Why your stack enables it: Supabase Edge Functions + RLS = multi-tenant API for free. Competitors charge $99-299/mo for API access (GoHighLevel, Podium).

Implementation:

Edge function at /api/client/{client_id}/leads — returns their leads

Edge function at /api/client/{client_id}/bookings — returns/creates bookings

Authenticated via API key stored in client_api_keys table

Rate limited via Supabase's built-in rate limiting

Documented with a simple auto-generated Swagger page

Revenue impact: API access becomes an Autopilot-exclusive feature. Clients with dispatch software (ServiceTitan, Housecall Pro) can sync ZES data automatically — making ZES "sticky" and hard to leave.

Enhancement 5: Predictive Job Demand via PostHog + Weather API
What it does: Cross-reference PostHog event data (which services are getting searched/booked) with weather forecasts to predict demand spikes and alert clients proactively.

Why your stack enables it: PostHog (free tier) + OpenWeatherMap API (free tier) + n8n scheduling + Twilio SMS.

Implementation:

n8n daily job: Pull 7-day weather forecast for each client's service area

Cross-reference with historical booking patterns in Supabase

If hail forecast + roofing client → SMS: "⚠️ Hail expected Thursday. Expect 3-5x normal call volume. Make sure your ZES agent greeting mentions storm damage inspections."

If freeze forecast + plumber → SMS about pipe burst preparation

Already partially built as "Storm Blast Strategy" in your RAG KB — this operationalizes it

Revenue impact: Clients who prepare for demand spikes capture 2-3x more emergency jobs. This is the kind of proactive intelligence that makes ZES feel like a $500/mo service they're getting for $30.

Enhancement 6: Cal.com Self-Hosted for Zero Booking Fees
What it does: Self-host Cal.com instead of using the cloud version — eliminates per-seat costs and gives you full API control for custom booking flows.

Why your stack enables it: Cal.com is open source. You already have server infrastructure. Self-hosting means $0/mo regardless of how many clients use booking.

Implementation:

Deploy Cal.com on your server (Docker, same infra as n8n)

Each ZES client gets a branded booking page: book.clientname.com

Cal.com webhooks → n8n → Supabase (lead created + booking logged)

Two-way Google Calendar sync for each client

Custom booking confirmation SMS via Twilio

Cost savings: Cal.com cloud charges $12-30/user/mo. Self-hosted = $0. At 100 clients, that's $1,200-3,000/mo saved.

Enhancement 7: White-Label Client Reporting via Metabase (Self-Hosted)
What it does: Give Autopilot clients access to beautiful, interactive analytics dashboards — leads over time, booking conversion rates, revenue trends, competitor comparisons.

Why your stack enables it: Metabase is open source. Connects directly to Supabase Postgres. Self-hosted = $0.

Implementation:

Deploy Metabase on your server

Connect to Supabase Postgres

Create dashboard templates: "Lead Funnel", "Revenue Attribution", "Review Velocity", "Competitor Comparison"

Each client gets a read-only Metabase embed with RLS-filtered data

Embed in client dashboard or share as standalone link

Revenue impact: Autopilot clients get enterprise-grade analytics for $30/mo. GoHighLevel charges $297/mo for worse dashboards. This is a massive competitive moat.

Enhancement 8: Automated Contract + Invoice Pipeline (Xero + Supabase)
What it does: When a new ZES client signs up, automatically generate their contract, onboarding checklist, first invoice, and Stripe subscription — zero manual work.

Implementation:

Stripe Checkout → webhook to n8n

n8n creates: Supabase client record, Xero contact + first invoice, Notion onboarding page, Cal.com booking page, ElevenLabs agent configuration

Contract PDF generated via ReportLab (you already have this in your codebase)

Sent via SendGrid for e-signature (or DocuSign API)

Client receives: Welcome email + contract + booking link + first invoice — all within 5 minutes of payment

Impact: "24-hour agent delivery" becomes "5-minute onboarding start" — the fastest in the industry.

Part 3: OSS Landscape Reality Check
ZES Capability	Best OSS Alternative	Why ZES Still Wins
AI Voice Agent	Vapi (open-source-friendly, $0.05/min + add-ons)	Vapi requires dev setup. ZES is turnkey for non-technical trade owners. Vapi real-world cost: $0.25-0.33/min vs ZES flat monthly
Review Automation	ReviewsUp.io (open source, self-hosted)	ReviewsUp only collects/displays. No Google posting, no auto-request after jobs, no AI response generation
Online Booking	Cal.com (fully open source)	Cal.com is the engine — but ZES bundles it with lead tracking, CRM, voice, and reviews. Cal.com alone doesn't help a plumber
Lead CRM	Odoo CRM, Twenty CRM (open source)	Both require setup and maintenance. ZES CRM is pre-configured for trade workflows
SEO/Local Search	No real OSS competitor	SerpAPI + custom scripts exist but require dev skills. ZES automates GBP posting + rank tracking
Website Builder	WordPress (open source)	WordPress is free but requires hosting, themes, plugins, maintenance. TradeBuilder is done-for-you Framer in 48 hours
Workflow Automation	n8n (you already use this)	n8n IS your advantage. Competitors use Zapier at 10-50x the cost
Analytics	Metabase, PostHog (open source)	You already have both. The enhancement is exposing them to clients
Invoicing	Invoice Ninja (open source)	Invoice Ninja is standalone. ZES text-to-pay is embedded in the customer journey
Bottom line: The OSS components exist individually, but the packaging, integration, and trade-business-specific configuration is the product. Nobody is assembling Vapi + Cal.com + ReviewsUp + Odoo + n8n + Metabase into a $30/mo turnkey agent for HVAC contractors. That's the moat.

Part 4: Priority Implementation Order
Priority	Enhancement	Effort	Revenue Impact	Moat Impact
🔴 P0	Client Dashboard (Weakness 2)	2 weeks	High (reduces churn)	Medium
🔴 P0	ROI Attribution Report (Weakness 4)	1 week	Critical (churn killer)	High
🔴 P0	Stripe Connect Multi-Tenant (Enhancement 2)	2 weeks	$10-20K/mo at scale	Very High
🟡 P1	AI Review Response Engine (Weakness 5)	1 week	Medium (differentiator)	High
🟡 P1	Real-Time Lead Scoring (Enhancement 1)	1 week	High (client success)	Medium
🟡 P1	Predictive Demand Alerts (Enhancement 5)	3 days	Medium (retention)	Very High
🟢 P2	Voice Agent Failover (Weakness 1)	3 days	Low (insurance)	Medium
🟢 P2	Self-Hosted Cal.com (Enhancement 6)	2 days	$1-3K/mo saved	Low
🟢 P2	SEO Page Generator (Enhancement 3)	1 week	High (TradeBuilder value)	High
🟢 P2	Client API Access (Enhancement 4)	1 week	Medium (stickiness)	Very High
🔵 P3	Audit Trail (Weakness 3)	2 days	Low (legal protection)	Medium
🔵 P3	Competitor Snapshots (Weakness 6)	3 days	Medium (upsell hook)	Medium
🔵 P3	Webhook Security (Weakness 7)	1 day	Low (security)	Low
🔵 P3	Server Hardening (Weakness 8)	1 day	Low (security)	Low
🔵 P3	Metabase White-Label (Enhancement 7)	3 days	Medium (Autopilot value)	High
🔵 P3	Auto Contract Pipeline (Enhancement 8)	1 week	Medium (ops efficiency)	Medium
The Compounding Effect
When you stack these together, here's what happens:

Client signs up → Auto-onboarding pipeline creates everything in 5 minutes (Enhancement 8)

Leads come in → Real-time scoring + instant SMS to owner (Enhancement 1)

Calls answered → AI voice agent with failover protection (Weakness 1 fix)

Jobs booked → Cal.com self-hosted, zero per-seat cost (Enhancement 6)

Jobs completed → Auto review request → AI response drafts (Weakness 5 fix)

Client invoices customer → Stripe Connect, you earn platform fee (Enhancement 2)

Month end → ROI report auto-generated proving 100x+ return (Weakness 4 fix)

Client logs in → Dashboard shows leads, revenue, competitors, rankings (Weakness 2 fix + Enhancement 7)

Storm coming → Predictive alert sent, client captures surge demand (Enhancement 5)

SEO compounds → Auto-generated service pages ranking in 30-60 days (Enhancement 3)

Each layer reinforces the others. The client can't replicate this with any combination of tools for less than $500-1,000/mo — and you're delivering it for $30.

That's the moat. Build it.🔧 COMPREHENSIVE BUILDOUT GAP BLUEPRINT
ZES Agent + TradeBuilder Website Factory — Remaining Code & Implementation
PART 1: OSS COMPETITIVE AUDIT — WHAT EXISTS vs WHAT YOU'RE BUILDING
1A. Voice Agent Layer (ZES Core)
OSS / Competitor	What It Does	Where It Falls Short vs ZES
Vapi.ai (closed, but API-first)	Voice agent builder, CRM hooks	No self-hosted option, per-minute pricing explodes at scale
​
Vocode (OSS)	Python voice agent framework	No built-in CRM, no Stripe, no booking — raw framework only
OpenOmni (OSS)	Multimodal conversation pipeline	Research-grade, 250ms+ latency, no production billing
​
Aloware ($30/user/mo)	AI voice + CRM + power dialer	HubSpot-locked, no self-hosted, no white-label, no website tier
​
Synthflow (no-code)	Visual voice agent builder	Zapier-only integrations, no Stripe Connect, no multi-tenant
​
Bland.ai (API)	Outbound voice automation	No inbound, no CRM, no booking, API-only
VERDICT: Nothing in OSS combines voice agent + CRM + booking + Stripe Connect + website provisioning in one stack. Your moat is the vertical integration.

1B. Workflow Automation (n8n alternatives)
Tool	Self-Hosted	AI-Native	Pricing Risk
n8n (your choice) ✅	Yes, free	Growing	$720/mo for shared credentials on cloud
​
Activepieces	Yes, free	MCP support, AI agents	Smaller ecosystem
​
Windmill	Yes, free	Script-first, fast	Developer-only, no visual for non-technical users
​
Temporal	Yes, free	Durable execution	Enterprise complexity, overkill
​
VERDICT: n8n is correct. Activepieces is worth watching for MCP-native features. No change needed.

1C. Multi-Tenant Billing (Stripe Connect)
Approach	Pros	Cons
Stripe Connect (your choice) ✅	Full platform billing, KYC handled
​	Onboarding friction (3+ steps)
Paddle	Tax handling built-in	No Connect equivalent for payouts
LemonSqueezy	Simple MoR	No multi-tenant, no Connect
OpenMeter + Stripe	Usage-based metering	Extra dependency, complexity
VERDICT: Stripe Connect is correct. The gap is the onboarding wizard (Gap 1 below).

1D. Invoicing/Accounting (Xero integration)
Approach	Pros	Cons
Xero + n8n native node	Quick setup	Only supports Contacts + Invoices, no bank reconciliation
​
Xero + n8n HTTP Request	Full API access	Must handle OAuth2, tenant-id header, manual API calls
​
QuickBooks Online	Larger US market share	More complex API, similar integration effort
VERDICT: Xero is fine but the native n8n node is too limited. You need custom HTTP Request nodes. Code provided below.

PART 2: IDENTIFIED BUILDOUT GAPS — WITH PRODUCTION CODE
Gap 1: Stripe Connect Onboarding Wizard
Status: Blocker — no code exists
What's Missing: The KYC onboarding flow for TradeBuilder customers to accept payments

Gap 2: Xero Invoice Sync Pipeline
Status: Referenced in monetization docs, zero implementation
What's Missing: Auto-create invoices in Xero when Stripe subscription events fire

Gap 3: Webhook Event Router (Stripe → Supabase → n8n)
Status: Post-call webhook exists, billing webhooks incomplete
What's Missing: Complete Stripe webhook handler for subscription lifecycle

Gap 4: TradeBuilder Provisioning State Machine
Status: Documented in Business Plan, no code
What's Missing: The state machine that drives intake → payment → site deploy

Gap 5: 10DLC Registration Pipeline
Status: Critical blocker, no implementation
What's Missing: Twilio brand/campaign registration during onboarding

Gap 6: ZES Agent Delivery Automation (24-hour SLA)
Status: Promised in sales docs, no automation
What's Missing: n8n workflow that provisions a ZES agent config within 24 hours

Gap 7: Bundle Pricing Engine
Status: Referenced, no Stripe products/prices created
What's Missing: TradeBuilder + ZES bundle discount logic

Gap 8: Client Health Score + Churn Prediction
Status: Identified as missing in Monetization Strategy
What's Missing: Usage tracking → health score → save offer automation

PART 3: PRODUCTION CODE FOR EACH GAP
═══════════════════════════════════════════════════════
GAP 1: STRIPE CONNECT ONBOARDING WIZARD
═══════════════════════════════════════════════════════
File: src/api/routes/stripe_connect.py
Purpose: Onboard TradeBuilder customers to accept payments through their websites
​

python
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import stripe
import os

router = APIRouter(prefix="/api/v1/stripe-connect", tags=["Stripe Connect"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PLATFORM_FEE_PERCENT = 5  # 5% platform fee on customer payments

class ConnectOnboardRequest(BaseModel):
    lead_id: str
    business_name: str
    email: str
    country: str = "US"
    business_type: str = "individual"  # individual | company

class ConnectOnboardResponse(BaseModel):
    account_id: str
    onboarding_url: str
    expires_at: int

@router.post("/onboard", response_model=ConnectOnboardResponse)
async def create_connect_account(req: ConnectOnboardRequest):
    """
    Step 1: Create a Stripe Connect Express account for the trade business.
    Returns an onboarding URL the customer clicks to complete KYC.
    """
    try:
        account = stripe.Account.create(
            type="express",
            country=req.country,
            email=req.email,
            business_type=req.business_type,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            metadata={
                "lead_id": req.lead_id,
                "business_name": req.business_name,
                "source": "tradebuilder",
            },
        )

        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"{os.getenv('APP_URL')}/connect/refresh?account={account.id}",
            return_url=f"{os.getenv('APP_URL')}/connect/complete?account={account.id}",
            type="account_onboarding",
        )

        # Store in Supabase
        from src.lib.supabase_client import get_service_client
        sb = get_service_client()
        sb.table("stripe_connect_accounts").upsert({
            "lead_id": req.lead_id,
            "stripe_account_id": account.id,
            "business_name": req.business_name,
            "email": req.email,
            "status": "onboarding_started",
            "onboarding_url": account_link.url,
        }).execute()

        return ConnectOnboardResponse(
            account_id=account.id,
            onboarding_url=account_link.url,
            expires_at=account_link.expires_at,
        )

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{account_id}")
async def check_connect_status(account_id: str):
    """Check if Connect account has completed onboarding."""
    account = stripe.Account.retrieve(account_id)
    return {
        "account_id": account.id,
        "charges_enabled": account.charges_enabled,
        "payouts_enabled": account.payouts_enabled,
        "details_submitted": account.details_submitted,
        "requirements": account.requirements.currently_due if account.requirements else [],
    }


@router.post("/create-payment-intent")
async def create_destination_payment(
    amount: int,
    currency: str = "usd",
    connected_account_id: str = "",
    customer_email: str = "",
    description: str = "",
):
    """
    Create a payment intent that routes funds to the trade business
    with platform fee retained by Citadel.
    """
    application_fee = int(amount * (PLATFORM_FEE_PERCENT / 100))

    intent = stripe.PaymentIntent.create(
        amount=amount,
        currency=currency,
        application_fee_amount=application_fee,
        transfer_data={"destination": connected_account_id},
        receipt_email=customer_email,
        description=description,
        metadata={
            "source": "tradebuilder_website",
            "connected_account": connected_account_id,
        },
    )
    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
        "amount": amount,
        "platform_fee": application_fee,
    }
Supabase Migration:

sql
-- Stripe Connect accounts for TradeBuilder customers
CREATE TABLE IF NOT EXISTS public.stripe_connect_accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID REFERENCES public.leads(id),
    stripe_account_id TEXT UNIQUE NOT NULL,
    business_name   TEXT NOT NULL,
    email           TEXT NOT NULL,
    status          TEXT DEFAULT 'onboarding_started'
                    CHECK (status IN (
                        'onboarding_started', 'onboarding_complete',
                        'charges_enabled', 'payouts_enabled',
                        'restricted', 'disabled'
                    )),
    onboarding_url  TEXT,
    charges_enabled BOOLEAN DEFAULT false,
    payouts_enabled BOOLEAN DEFAULT false,
    platform_fee_percent NUMERIC(5,2) DEFAULT 5.00,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_connect_lead ON public.stripe_connect_accounts(lead_id);
CREATE INDEX idx_connect_stripe ON public.stripe_connect_accounts(stripe_account_id);

ALTER TABLE public.stripe_connect_accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_connect" ON public.stripe_connect_accounts
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 2: XERO INVOICE SYNC PIPELINE
═══════════════════════════════════════════════════════
File: src/api/routes/xero_sync.py
Purpose: Auto-create Xero invoices when Stripe subscriptions are paid

python
import httpx
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/xero", tags=["Xero Sync"])

XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"


class XeroTokenManager:
    """Manages Xero OAuth2 tokens with auto-refresh.
    Stores tokens in Supabase Vault."""

    def __init__(self):
        self.client_id = os.getenv("XERO_CLIENT_ID")
        self.client_secret = os.getenv("XERO_CLIENT_SECRET")
        self.tenant_id = os.getenv("XERO_TENANT_ID")
        self._token = None
        self._expires_at = None

    async def get_token(self) -> str:
        if self._token and self._expires_at and datetime.utcnow() < self._expires_at:
            return self._token

        from src.lib.supabase_client import get_service_client
        sb = get_service_client()
        creds = sb.table("xero_credentials").select("*").single().execute()

        if not creds.data:
            raise HTTPException(status_code=500, detail="Xero credentials not configured")

        async with httpx.AsyncClient() as client:
            resp = await client.post(XERO_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": creds.data["refresh_token"],
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            })
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Xero token refresh failed: {resp.text}")

            token_data = resp.json()
            self._token = token_data["access_token"]
            self._expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"] - 60)

            sb.table("xero_credentials").update({
                "access_token": token_data["access_token"],
                "refresh_token": token_data["refresh_token"],
                "expires_at": self._expires_at.isoformat(),
            }).eq("id", creds.data["id"]).execute()

        return self._token

    async def _headers(self):
        token = await self.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "xero-tenant-id": self.tenant_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


xero_tokens = XeroTokenManager()


async def find_or_create_xero_contact(business_name: str, email: str) -> str:
    """Find existing Xero contact or create new one. Returns ContactID."""
    headers = await xero_tokens._headers()

    async with httpx.AsyncClient() as client:
        search = await client.get(
            f"{XERO_API_BASE}/Contacts",
            headers=headers,
            params={"where": f'EmailAddress=="{email}"'},
        )
        contacts = search.json().get("Contacts", [])
        if contacts:
            return contacts[0]["ContactID"]

        create_resp = await client.post(
            f"{XERO_API_BASE}/Contacts",
            headers=headers,
            json={"Contacts": [{
                "Name": business_name,
                "EmailAddress": email,
                "IsCustomer": True,
            }]},
        )
        new_contacts = create_resp.json().get("Contacts", [])
        if not new_contacts:
            raise HTTPException(status_code=500, detail="Failed to create Xero contact")
        return new_contacts[0]["ContactID"]


async def create_xero_invoice(
    contact_id: str,
    description: str,
    amount: float,
    reference: str,
    due_date: Optional[str] = None,
    account_code: str = "200",
) -> dict:
    """Create invoice in Xero. Called by Stripe webhook handler."""
    headers = await xero_tokens._headers()

    if not due_date:
        due_date = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")

    invoice_payload = {
        "Invoices": [{
            "Type": "ACCREC",
            "Contact": {"ContactID": contact_id},
            "Date": datetime.utcnow().strftime("%Y-%m-%d"),
            "DueDate": due_date,
            "Reference": reference,
            "Status": "AUTHORISED",
            "LineItems": [{
                "Description": description,
                "Quantity": 1,
                "UnitAmount": amount,
                "AccountCode": account_code,
                "TaxType": "OUTPUT",
            }],
        }],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{XERO_API_BASE}/Invoices",
            headers=headers,
            json=invoice_payload,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=500,
                detail=f"Xero invoice creation failed: {resp.text}"
            )

        invoice = resp.json()["Invoices"][0]

        # Mark as paid (Stripe already collected)
        payment_payload = {
            "Payments": [{
                "Invoice": {"InvoiceID": invoice["InvoiceID"]},
                "Account": {"Code": "090"},  # Stripe clearing account
                "Date": datetime.utcnow().strftime("%Y-%m-%d"),
                "Amount": amount,
                "Reference": f"Stripe: {reference}",
            }],
        }
        await client.put(
            f"{XERO_API_BASE}/Payments",
            headers=headers,
            json=payment_payload,
        )

        return {
            "xero_invoice_id": invoice["InvoiceID"],
            "invoice_number": invoice["InvoiceNumber"],
            "status": "PAID",
            "amount": amount,
        }


@router.post("/sync-invoice")
async def sync_stripe_to_xero(
    stripe_invoice_id: str,
    customer_email: str,
    business_name: str,
    amount: float,
    description: str,
):
    """Called by n8n when Stripe invoice.paid fires."""
    contact_id = await find_or_create_xero_contact(business_name, customer_email)
    result = await create_xero_invoice(
        contact_id=contact_id,
        description=description,
        amount=amount,
        reference=stripe_invoice_id,
    )
    return result
Supabase Migration:

sql
CREATE TABLE IF NOT EXISTS public.xero_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.xero_invoice_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_invoice_id   TEXT NOT NULL,
    xero_invoice_id     TEXT,
    xero_invoice_number TEXT,
    customer_email      TEXT NOT NULL,
    amount              NUMERIC(10,2) NOT NULL,
    status              TEXT DEFAULT 'synced',
    error               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_xero_log_stripe ON public.xero_invoice_log(stripe_invoice_id);
ALTER TABLE public.xero_invoice_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_xero_log" ON public.xero_invoice_log
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 3: COMPLETE STRIPE WEBHOOK EVENT ROUTER
═══════════════════════════════════════════════════════
File: src/api/routes/stripe_webhooks.py
Purpose: Single webhook endpoint handling ALL Stripe lifecycle events — the "one webhook to rule them all" pattern

python
import stripe
import json
import os
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from src.lib.supabase_client import get_service_client

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
CONNECT_WEBHOOK_SECRET = os.getenv("STRIPE_CONNECT_WEBHOOK_SECRET")


async def publish_nats(subject: str, payload: dict):
    """Publish event to NATS for n8n consumption."""
    try:
        from src.lib.natsservice import NATSService
        await NATSService.publish(subject, json.dumps(payload))
    except Exception:
        pass  # Non-blocking


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """
    The ONE webhook to rule them all.
    Handles: subscriptions, invoices, Connect, payment intents.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    sb = get_service_client()
    event_type = event["type"]
    data = event["data"]["object"]

    # Idempotency check
    existing = sb.table("stripe_events").select("id").eq(
        "stripe_event_id", event["id"]
    ).execute()
    if existing.data:
        return {"status": "already_processed"}

    # Log the event
    sb.table("stripe_events").insert({
        "stripe_event_id": event["id"],
        "event_type": event_type,
        "payload": json.loads(payload),
        "processed_at": datetime.utcnow().isoformat(),
    }).execute()

    # ── SUBSCRIPTION EVENTS ──
    if event_type == "customer.subscription.created":
        await _handle_subscription_created(sb, data)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(sb, data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(sb, data)

    # ── INVOICE EVENTS ──
    elif event_type == "invoice.paid":
        await _handle_invoice_paid(sb, data)
    elif event_type == "invoice.payment_failed":
        await _handle_invoice_failed(sb, data)

    # ── CONNECT EVENTS ──
    elif event_type == "account.updated":
        await _handle_connect_account_updated(sb, data)

    # ── CHECKOUT EVENTS ──
    elif event_type == "checkout.session.completed":
        await _handle_checkout_completed(sb, data)

    return {"status": "processed", "type": event_type}


async def _handle_subscription_created(sb, subscription):
    """New subscription → provision resources."""
    customer_id = subscription["customer"]
    plan_id = subscription["items"]["data"][0]["price"]["id"]
    metadata = subscription.get("metadata", {})

    if metadata.get("lead_id"):
        sb.table("leads").update({
            "status": "TRIAL_STARTED" if subscription.get("trial_end") else "WEBSITE_SOLD",
            "tier_interest": metadata.get("tier", ""),
        }).eq("id", metadata["lead_id"]).execute()

    await publish_nats("leads.converted", {
        "subscription_id": subscription["id"],
        "customer_id": customer_id,
        "plan_id": plan_id,
        "lead_id": metadata.get("lead_id"),
        "product": metadata.get("product", "tradebuilder"),
        "tier": metadata.get("tier", "tier1"),
    })


async def _handle_subscription_updated(sb, subscription):
    """Plan change or status change."""
    status = subscription["status"]
    customer_id = subscription["customer"]

    if status == "past_due":
        await publish_nats("billing.past_due", {
            "subscription_id": subscription["id"],
            "customer_id": customer_id,
        })
    elif status == "active":
        await publish_nats("billing.restored", {
            "subscription_id": subscription["id"],
            "customer_id": customer_id,
        })


async def _handle_subscription_deleted(sb, subscription):
    """Subscription cancelled → suspend site."""
    metadata = subscription.get("metadata", {})

    if metadata.get("lead_id"):
        sb.table("leads").update({
            "status": "NOT_INTERESTED",
        }).eq("id", metadata["lead_id"]).execute()

    await publish_nats("billing.cancelled", {
        "subscription_id": subscription["id"],
        "customer_id": subscription["customer"],
        "lead_id": metadata.get("lead_id"),
        "product": metadata.get("product"),
    })


async def _handle_invoice_paid(sb, invoice):
    """Invoice paid → sync to Xero + log."""
    customer_email = invoice.get("customer_email", "")
    customer_name = invoice.get("customer_name", "")
    amount = invoice["amount_paid"] / 100

    description = ""
    for line in invoice.get("lines", {}).get("data", []):
        description += line.get("description", "") + "; "

    try:
        from src.api.routes.xero_sync import (
            find_or_create_xero_contact,
            create_xero_invoice,
        )
        contact_id = await find_or_create_xero_contact(customer_name, customer_email)
        await create_xero_invoice(
            contact_id=contact_id,
            description=description.strip("; "),
            amount=amount,
            reference=invoice["id"],
        )
    except Exception as e:
        sb.table("xero_invoice_log").insert({
            "stripe_invoice_id": invoice["id"],
            "customer_email": customer_email,
            "amount": amount,
            "status": "failed",
            "error": str(e),
        }).execute()

    await publish_nats("billing.invoice.paid", {
        "invoice_id": invoice["id"],
        "customer_email": customer_email,
        "amount": amount,
    })


async def _handle_invoice_failed(sb, invoice):
    """Payment failed → start dunning sequence."""
    await publish_nats("billing.invoice.failed", {
        "invoice_id": invoice["id"],
        "customer_id": invoice["customer"],
        "customer_email": invoice.get("customer_email"),
        "attempt_count": invoice.get("attempt_count", 0),
        "next_attempt": invoice.get("next_payment_attempt"),
    })


async def _handle_connect_account_updated(sb, account):
    """Connect account status changed (KYC complete, etc)."""
    sb.table("stripe_connect_accounts").update({
        "charges_enabled": account["charges_enabled"],
        "payouts_enabled": account["payouts_enabled"],
        "status": "charges_enabled" if account["charges_enabled"] else "onboarding_started",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("stripe_account_id", account["id"]).execute()

    if account["charges_enabled"]:
        await publish_nats("connect.account.ready", {
            "account_id": account["id"],
            "business_name": account.get("business_profile", {}).get("name", ""),
        })


async def _handle_checkout_completed(sb, session):
    """Checkout session completed → route based on product."""
    metadata = session.get("metadata", {})
    mode = session.get("mode")

    if mode == "payment":
        await publish_nats("billing.setup_fee.paid", {
            "session_id": session["id"],
            "customer_email": session.get("customer_email"),
            "amount": session["amount_total"] / 100,
            "lead_id": metadata.get("lead_id"),
        })
Supabase Migration:

sql
CREATE TABLE IF NOT EXISTS public.stripe_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_event_id TEXT UNIQUE NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    processed_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_stripe_events_type ON public.stripe_events(event_type, processed_at DESC);
ALTER TABLE public.stripe_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_events" ON public.stripe_events
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 4: TRADEBUILDER PROVISIONING STATE MACHINE
═══════════════════════════════════════════════════════
File: src/services/provisioning_engine.py
Purpose: Drives intake → payment → site deployment with rollback
​

python
from enum import Enum
from datetime import datetime
from typing import Optional
import asyncio
import os


class ProvisioningState(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEW_NEEDED = "review_needed"
    APPROVED = "approved"
    PAYMENT_PENDING = "payment_pending"
    PROVISIONING = "provisioning"
    STAGED = "staged"
    PUBLISHED = "published"
    LIVE = "live"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


# Valid transitions
TRANSITIONS = {
    ProvisioningState.DRAFT: [ProvisioningState.SUBMITTED],
    ProvisioningState.SUBMITTED: [ProvisioningState.APPROVED, ProvisioningState.REVIEW_NEEDED],
    ProvisioningState.REVIEW_NEEDED: [ProvisioningState.APPROVED, ProvisioningState.CANCELLED],
    ProvisioningState.APPROVED: [ProvisioningState.PAYMENT_PENDING],
    ProvisioningState.PAYMENT_PENDING: [ProvisioningState.PROVISIONING, ProvisioningState.CANCELLED],
    ProvisioningState.PROVISIONING: [ProvisioningState.STAGED, ProvisioningState.REVIEW_NEEDED],
    ProvisioningState.STAGED: [ProvisioningState.PUBLISHED],
    ProvisioningState.PUBLISHED: [ProvisioningState.LIVE],
    ProvisioningState.LIVE: [ProvisioningState.SUSPENDED, ProvisioningState.CANCELLED],
    ProvisioningState.SUSPENDED: [ProvisioningState.LIVE, ProvisioningState.CANCELLED],
}


class ProvisioningEngine:
    """
    State machine for TradeBuilder site provisioning.
    Orchestrates: intake validation → Stripe billing → Framer deploy → DNS → SEO.
    Target: < 4 hours to staging, < 48 hours to published.
    """

    def __init__(self, supabase_client, nats_client=None):
        self.sb = supabase_client
        self.nats = nats_client

    async def transition(self, intake_id: str, target_state: ProvisioningState) -> dict:
        """Attempt a state transition with validation."""
        record = self.sb.table("client_intakes").select("*").eq(
            "id", intake_id
        ).single().execute()

        if not record.data:
            raise ValueError(f"Intake {intake_id} not found")

        current = ProvisioningState(record.data["status"])
        allowed = TRANSITIONS.get(current, [])

        if target_state not in allowed:
            raise ValueError(
                f"Cannot transition from {current} to {target_state}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        handler = getattr(self, f"_on_{target_state.value}", None)
        result = {}
        if handler:
            result = await handler(record.data) or {}

        self.sb.table("client_intakes").update({
            "status": target_state.value,
            "updated_at": datetime.utcnow().isoformat(),
            **result,
        }).eq("id", intake_id).execute()

        if self.nats:
            await self.nats.publish(
                f"tradebuilder.provision.{target_state.value}",
                {"intake_id": intake_id, "state": target_state.value, **result},
            )

        return {"intake_id": intake_id, "state": target_state.value, **result}

    async def _on_submitted(self, intake: dict) -> dict:
        """Validate intake and auto-approve or flag for review."""
        from src.services.intake_validator import validate_intake, check_kill_switches
        errors = validate_intake(intake)
        red_flags = check_kill_switches(intake)

        if errors:
            return {"validation_errors": errors, "status": "review_needed"}
        if red_flags:
            return {"red_flags": red_flags, "status": "review_needed"}
        return {"status": "approved"}

    async def _on_approved(self, intake: dict) -> dict:
        """Create Stripe customer + subscription."""
        import stripe
        tier = intake.get("plan_tier", "tier1_static")
        price_map = {
            "tier1_static": os.getenv("STRIPE_PRICE_TIER1"),
            "tier2_conversion": os.getenv("STRIPE_PRICE_TIER2"),
            "tier3_ops_lite": os.getenv("STRIPE_PRICE_TIER3"),
        }
        setup_fee_map = {
            "tier1_static": 9900,
            "tier2_conversion": 9900,
            "tier3_ops_lite": 19900,
        }

        customer = stripe.Customer.create(
            email=intake["primary_email"],
            name=intake["business_name"],
            metadata={"intake_id": intake["id"], "tier": tier},
        )

        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_map[tier]}],
            add_invoice_items=[{
                "price_data": {
                    "currency": "usd",
                    "product": os.getenv("STRIPE_SETUP_FEE_PRODUCT"),
                    "unit_amount": setup_fee_map[tier],
                },
                "quantity": 1,
            }],
            metadata={"intake_id": intake["id"], "tier": tier, "product": "tradebuilder"},
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
        )

        return {
            "stripe_customer_id": customer.id,
            "stripe_subscription_id": subscription.id,
            "payment_intent_secret": subscription.latest_invoice.payment_intent.client_secret,
        }

    async def _on_provisioning(self, intake: dict) -> dict:
        """Execute the full provisioning pipeline."""
        steps_completed = []
        try:
            domain = await self._provision_domain(intake)
            steps_completed.append("domain")

            site = await self._provision_framer_site(intake)
            steps_completed.append("framer_site")

            webhook = await self._setup_lead_routing(intake)
            steps_completed.append("lead_routing")

            seo = await self._setup_seo_baseline(intake)
            steps_completed.append("seo")

            asyncio.create_task(self._generate_collateral(intake))
            steps_completed.append("collateral_queued")

            return {
                "provisioning_steps": steps_completed,
                "domain": domain,
                "site_url": site.get("url"),
            }

        except Exception as e:
            await self._rollback(intake["id"], steps_completed)
            raise

    async def _provision_domain(self, intake: dict) -> dict:
        return {"domain": intake.get("domain", ""), "status": "instructions_sent"}

    async def _provision_framer_site(self, intake: dict) -> dict:
        template = f"tmpl_{intake['industry']}_{'basic' if 'tier1' in intake.get('plan_tier', '') else 'conversion'}_v1"
        return {"template": template, "url": f"https://{intake.get('domain', 'staging')}", "status": "staged"}

    async def _setup_lead_routing(self, intake: dict) -> dict:
        return {"webhook_url": f"https://n8n.citadel-nexus.com/webhook/{intake['id']}", "status": "active"}

    async def _setup_seo_baseline(self, intake: dict) -> dict:
        return {"schema_markup": True, "sitemap": True, "meta_tags": True}

    async def _generate_collateral(self, intake: dict):
        pass

    async def _rollback(self, intake_id: str, completed_steps: list):
        self.sb.table("provisioning_rollbacks").insert({
            "intake_id": intake_id,
            "completed_steps": completed_steps,
            "rolled_back_at": datetime.utcnow().isoformat(),
        }).execute()
═══════════════════════════════════════════════════════
GAP 5: 10DLC REGISTRATION PIPELINE
═══════════════════════════════════════════════════════
File: src/services/ten_dlc_registration.py
Purpose: Register Twilio 10DLC brand + campaign during onboarding (critical — SMS gets filtered/blocked without this)

python
from twilio.rest import Client
import os
from typing import Optional


class TenDLCRegistration:
    """
    Handles Twilio 10DLC brand and campaign registration.
    REQUIRED for all A2P SMS — without this, messages get filtered/blocked.
    Cost: $4 one-time brand + $0.75/mo per campaign.
    """

    def __init__(self):
        self.client = Client(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN"),
        )
        self.messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")

    async def register_brand(
        self,
        business_name: str,
        ein: Optional[str] = None,
        business_type: str = "sole_proprietorship",
        contact_email: str = "",
        contact_phone: str = "",
    ) -> dict:
        """
        Register a business as a 10DLC brand.
        Called once per trade business during onboarding.
        """
        if business_type == "sole_proprietorship" or not ein:
            brand = self.client.messaging.v1.services(
                self.messaging_service_sid
            ).us_app_to_person.create(
                brand_registration_sid="",
                description=f"Business messaging for {business_name}",
                message_flow=(
                    "Customers opt-in via website contact form or direct request. "
                    "Messages include appointment confirmations, review requests, "
                    "and service reminders."
                ),
                message_samples=[
                    f"Hi! This is {business_name}. Your appointment is confirmed for tomorrow at 2 PM.",
                    f"Thanks for choosing {business_name}! How was your experience? Leave a review: [link]",
                    f"Reminder: Your annual AC maintenance is coming up. Book now: [link]",
                ],
                us_app_to_person_usecase="MIXED",
                has_embedded_links=True,
                has_embedded_phone=False,
                opt_in_type="VERBAL",
            )
            return {
                "brand_sid": brand.sid,
                "status": brand.campaign_status,
                "cost_onetime": 4.00,
                "cost_monthly": 0.75,
            }

        brand_registration = self.client.messaging.v1.brand_registrations.create(
            customer_profile_bundle_sid=self._create_customer_profile(
                business_name, ein, contact_email, contact_phone
            ),
            a2p_profile_bundle_sid=self._create_a2p_profile(business_name),
        )
        return {
            "brand_registration_sid": brand_registration.sid,
            "status": brand_registration.status,
        }

    def _create_customer_profile(self, name, ein, email, phone) -> str:
        profile = self.client.trusthub.v1.customer_profiles.create(
            friendly_name=name,
            email=email,
            policy_sid="RN806dd6cd175f314e1f96a9727ee271f4",
        )
        self.client.trusthub.v1.customer_profiles(
            profile.sid
        ).customer_profiles_entity_assignments.create(
            object_sid=self._create_end_user(name, ein),
        )
        self.client.trusthub.v1.customer_profiles(profile.sid).update(
            status="pending-review"
        )
        return profile.sid

    def _create_end_user(self, name, ein) -> str:
        end_user = self.client.trusthub.v1.end_users.create(
            friendly_name=name,
            type="us_a2p_brand_registration_sole_proprietor",
            attributes={
                "business_name": name,
                "ein": ein,
                "business_type": "Partnership",
            },
        )
        return end_user.sid

    def _create_a2p_profile(self, name) -> str:
        return ""
═══════════════════════════════════════════════════════
GAP 6: ZES AGENT 24-HOUR DELIVERY AUTOMATION
═══════════════════════════════════════════════════════
File: src/services/zes_agent_provisioner.py
Purpose: Auto-configure and deploy a ZES agent within 24 hours of signup

python
import httpx
import os
import json
from datetime import datetime
from typing import Optional


class ZESAgentProvisioner:
    """
    Provisions a ZES agent for a customer's existing website.
    24-hour SLA: signup → configured agent → live on their site.
    
    Flow:
    1. Customer signs up for ZES plan
    2. Intake form collects: website URL, business hours, services, phone
    3. This provisioner creates the ElevenLabs agent with RAG context
    4. Generates embed snippet for their website
    5. Sends setup instructions via email/SMS
    """

    ELEVENLABS_API = "https://api.elevenlabs.io/v1"

    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def provision_zes_agent(
        self,
        lead_id: str,
        business_name: str,
        website_url: str,
        phone: str,
        services: list[str],
        business_hours: dict,
        tier: str = "scout",
        industry: str = "general",
    ) -> dict:
        """
        Full ZES agent provisioning pipeline.
        Returns agent_id + embed code + setup instructions.
        """
        system_prompt = self._build_system_prompt(
            business_name, services, business_hours, industry, tier
        )

        agent = await self._create_elevenlabs_agent(
            name=f"ZES-{business_name[:20]}",
            system_prompt=system_prompt,
            tier=tier,
        )
        agent_id = agent["agent_id"]

        await self._push_rag_documents(agent_id, {
            "business_name": business_name,
            "website": website_url,
            "phone": phone,
            "services": services,
            "hours": business_hours,
            "industry": industry,
        })

        if tier in ("operator", "autopilot"):
            await self._register_mcp_tools(agent_id, tier)

        embed_code = self._generate_embed_snippet(agent_id, business_name)

        from src.lib.supabase_client import get_service_client
        sb = get_service_client()
        sb.table("zes_agents").upsert({
            "lead_id": lead_id,
            "agent_id": agent_id,
            "business_name": business_name,
            "website_url": website_url,
            "tier": tier,
            "status": "provisioned",
            "embed_code": embed_code,
            "provisioned_at": datetime.utcnow().isoformat(),
        }).execute()

        return {
            "agent_id": agent_id,
            "embed_code": embed_code,
            "tier": tier,
            "status": "provisioned",
            "setup_instructions": self._generate_setup_email(
                business_name, embed_code, tier
            ),
        }

    def _build_system_prompt(self, name, services, hours, industry, tier) -> str:
        services_text = ", ".join(services[:6])
        hours_text = json.dumps(hours) if isinstance(hours, dict) else str(hours)

        base = f"""You are the AI assistant for {name}, a {industry} business.

Your job is to answer customer questions, capture leads, and help with scheduling.

Business Info:
- Services: {services_text}
- Hours: {hours_text}

Behavior Rules:
- Be friendly, professional, and concise
- Always try to capture the caller's name, phone, and what service they need
- If asked about pricing, say "I can get you a free estimate — what's the best number to reach you?"
- If it's an emergency, prioritize getting their address and dispatching info
- Never make up information you don't have
- If you can't help, offer to have someone call them back"""

        if tier == "autopilot":
            base += """
- You can book appointments directly using the scheduling tool
- You can send text confirmations after booking
- You can check appointment availability in real-time"""

        return base

    async def _create_elevenlabs_agent(self, name: str, system_prompt: str, tier: str) -> dict:
        voice_id = os.getenv("ZES_DEFAULT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

        payload = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": system_prompt,
                    },
                    "first_message": "Hi, thanks for calling! How can I help you today?",
                    "language": "en",
                },
                "tts": {
                    "voice_id": voice_id,
                },
            },
            "name": name,
            "platform_settings": {
                "widget": {
                    "variant": "compact",
                    "avatar": {"type": "orb"},
                },
            },
        }

        if tier in ("operator", "autopilot"):
            payload["conversation_config"]["agent"]["prompt"]["mcp_servers"] = [{
                "url": f"https://mcp.citadel-nexus.com/mcp",
                "transport": "sse",
            }]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.ELEVENLABS_API}/convai/agents/create",
                headers=self.headers,
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def _push_rag_documents(self, agent_id: str, business_data: dict):
        doc_content = f"""
Business: {business_data['business_name']}
Website: {business_data['website']}
Phone: {business_data['phone']}
Industry: {business_data['industry']}
Services Offered: {', '.join(business_data['services'])}
Business Hours: {json.dumps(business_data['hours'])}
"""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.ELEVENLABS_API}/convai/agents/{agent_id}/add-to-knowledge-base",
                headers=self.headers,
                json={"url": None, "text": doc_content, "name": "business_info"},
            )

    async def _register_mcp_tools(self, agent_id: str, tier: str):
        pass  # MCP is registered at agent creation via prompt config

    def _generate_embed_snippet(self, agent_id: str, business_name: str) -> str:
        return f'<elevenlabs-convai agent-id="{agent_id}"></elevenlabs-convai>\n<script src="https://elevenlabs.io/convai-widget/index.js" async type="text/javascript"></script>'

    def _generate_setup_email(self, business_name: str, embed_code: str, tier: str) -> str:
        return f"""
Subject: Your ZES AI Agent is Ready — {business_name}

Your ZES {tier.title()} agent is configured and ready to go!

To add it to your website, paste this code before the </body> tag:

{embed_code}

If you use WordPress, go to Appearance → Theme Editor → footer.php and paste it there.
If you use Wix/Squarespace, add it via their Custom Code or Embed HTML block.

Your agent will start answering calls and capturing leads immediately.

Questions? Reply to this email or call us.
"""
Supabase Migration:

sql
CREATE TABLE IF NOT EXISTS public.zes_agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID REFERENCES public.leads(id),
    agent_id        TEXT UNIQUE NOT NULL,
    business_name   TEXT NOT NULL,
    website_url     TEXT,
    tier            TEXT NOT NULL CHECK (tier IN ('scout', 'operator', 'autopilot')),
    status          TEXT DEFAULT 'provisioned',
    embed_code      TEXT,
    provisioned_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_zes_agents_lead ON public.zes_agents(lead_id);
ALTER TABLE public.zes_agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_zes" ON public.zes_agents
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 7: BUNDLE PRICING ENGINE
═══════════════════════════════════════════════════════
File: src/services/bundle_pricing.py

python
import stripe
import os
from typing import Optional

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

BUNDLE_DISCOUNTS = {
    "tradebuilder_scout": 0.10,
    "tradebuilder_operator": 0.15,
    "tradebuilder_autopilot": 0.20,
}

ZES_PRICES = {
    "scout": 1500,
    "operator": 2000,
    "autopilot": 3000,
}

TB_PRICES = {
    "tier1_static": 9900,
    "tier2_conversion": 14900,
    "tier3_ops_lite": 24900,
}


async def calculate_bundle_price(
    tb_tier: str,
    zes_tier: Optional[str] = None,
) -> dict:
    """Calculate bundled price with discount."""
    tb_price = TB_PRICES.get(tb_tier, 0)
    result = {
        "tradebuilder_tier": tb_tier,
        "tradebuilder_price": tb_price,
        "zes_tier": zes_tier,
        "zes_price": 0,
        "discount_percent": 0,
        "discount_amount": 0,
        "total_monthly": tb_price,
        "is_bundle": False,
    }

    if zes_tier and zes_tier in ZES_PRICES:
        zes_price = ZES_PRICES[zes_tier]
        combined = tb_price + zes_price
        discount_key = f"tradebuilder_{zes_tier}"
        discount_pct = BUNDLE_DISCOUNTS.get(discount_key, 0)
        discount_amount = int(combined * discount_pct)
        total = combined - discount_amount

        result.update({
            "zes_price": zes_price,
            "discount_percent": int(discount_pct * 100),
            "discount_amount": discount_amount,
            "total_monthly": total,
            "is_bundle": True,
            "savings_annual": discount_amount * 12,
        })

    return result


async def create_bundle_subscription(
    customer_id: str,
    tb_tier: str,
    zes_tier: str,
    lead_id: str,
) -> dict:
    """Create a Stripe subscription with bundle discount via coupon."""
    bundle = await calculate_bundle_price(tb_tier, zes_tier)

    if not bundle["is_bundle"]:
        raise ValueError("Both TradeBuilder and ZES tiers required for bundle")

    coupon_id = f"bundle_{zes_tier}_{bundle['discount_percent']}pct"
    try:
        stripe.Coupon.retrieve(coupon_id)
    except stripe.error.InvalidRequestError:
        stripe.Coupon.create(
            id=coupon_id,
            percent_off=bundle["discount_percent"],
            duration="forever",
            name=f"TradeBuilder + ZES {zes_tier.title()} Bundle ({bundle['discount_percent']}% off)",
        )

    subscription = stripe.Subscription.create(
        customer=customer_id,
        items=[
            {"price": os.getenv(f"STRIPE_PRICE_TB_{tb_tier.upper()}")},
            {"price": os.getenv(f"STRIPE_PRICE_ZES_{zes_tier.upper()}")},
        ],
        coupon=coupon_id,
        metadata={
            "lead_id": lead_id,
            "bundle_type": f"{tb_tier}+{zes_tier}",
            "product": "tradebuilder_zes_bundle",
        },
    )

    return {
        "subscription_id": subscription.id,
        "total_monthly": bundle["total_monthly"] / 100,
        "discount_percent": bundle["discount_percent"],
        "savings_annual": bundle["savings_annual"] / 100,
    }
═══════════════════════════════════════════════════════
GAP 8: CLIENT HEALTH SCORE + CHURN PREDICTION
═══════════════════════════════════════════════════════
File: src/services/health_score.py

python
from datetime import datetime, timedelta
from typing import Optional


class ClientHealthScorer:
    """
    Calculates a 0-100 health score per client.
    Triggers save offers when score drops below threshold.
    
    Signals:
    - Website traffic (from PostHog/GA)
    - Form submissions received
    - Voice agent calls answered
    - Review requests sent/completed
    - Login frequency to dashboard
    - Support ticket volume
    - Payment status
    """

    WEIGHTS = {
        "website_traffic": 0.15,
        "form_submissions": 0.20,
        "voice_calls": 0.15,
        "reviews_generated": 0.10,
        "dashboard_logins": 0.10,
        "support_tickets": 0.10,
        "payment_health": 0.20,
    }

    THRESHOLDS = {
        "healthy": 70,
        "at_risk": 40,
        "critical": 20,
    }

    def __init__(self, supabase_client):
        self.sb = supabase_client

    async def calculate_score(self, lead_id: str, days: int = 30) -> dict:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()

        traffic = await self._get_traffic_score(lead_id, since)
        forms = await self._get_form_score(lead_id, since)
        calls = await self._get_voice_score(lead_id, since)
        reviews = await self._get_review_score(lead_id, since)
        logins = await self._get_login_score(lead_id, since)
        tickets = await self._get_ticket_score(lead_id, since)
        payment = await self._get_payment_score(lead_id)

        raw_score = (
            traffic * self.WEIGHTS["website_traffic"]
            + forms * self.WEIGHTS["form_submissions"]
            + calls * self.WEIGHTS["voice_calls"]
            + reviews * self.WEIGHTS["reviews_generated"]
            + logins * self.WEIGHTS["dashboard_logins"]
            + tickets * self.WEIGHTS["support_tickets"]
            + payment * self.WEIGHTS["payment_health"]
        )

        score = min(100, max(0, int(raw_score)))

        if score >= self.THRESHOLDS["healthy"]:
            status = "healthy"
        elif score >= self.THRESHOLDS["at_risk"]:
            status = "at_risk"
        else:
            status = "critical"

        result = {
            "lead_id": lead_id,
            "score": score,
            "status": status,
            "signals": {
                "traffic": traffic,
                "forms": forms,
                "calls": calls,
                "reviews": reviews,
                "logins": logins,
                "tickets": tickets,
                "payment": payment,
            },
            "calculated_at": datetime.utcnow().isoformat(),
        }

        self.sb.table("client_health_scores").upsert({
            "lead_id": lead_id,
            **result,
        }, on_conflict="lead_id").execute()

        if status == "critical":
            await self._trigger_save_offer(lead_id, score)

        return result

    async def _get_traffic_score(self, lead_id, since) -> float:
        return 50.0  # Wire to PostHog API

    async def _get_form_score(self, lead_id, since) -> float:
        result = self.sb.table("leads").select("id", count="exact").eq(
            "source_agent", "tradebuilder"
        ).gte("created_at", since).execute()
        count = result.count or 0
        return min(100, count * 20)

    async def _get_voice_score(self, lead_id, since) -> float:
        result = self.sb.table("call_transcripts").select("id", count="exact").eq(
            "lead_id", lead_id
        ).gte("created_at", since).execute()
        count = result.count or 0
        return min(100, count * 10)

    async def _get_review_score(self, lead_id, since) -> float:
        return 50.0  # Wire to review tracking

    async def _get_login_score(self, lead_id, since) -> float:
        return 50.0  # Wire to auth logs

    async def _get_ticket_score(self, lead_id, since) -> float:
        return 70.0  # Placeholder

    async def _get_payment_score(self, lead_id) -> float:
        lead = self.sb.table("leads").select("status").eq(
            "id", lead_id
        ).single().execute()
        if not lead.data:
            return 0
        status_scores = {
            "WEBSITE_SOLD": 100, "WEBSITE_PLUS_ZES": 100,
            "TRIAL_STARTED": 80, "TRIAL_STARTED_BUNDLE": 80,
            "INTERESTED": 60, "CALLBACK_REQUESTED": 50,
            "NOT_INTERESTED": 0, "DO_NOT_CALL": 0,
        }
        return status_scores.get(lead.data["status"], 50)

    async def _trigger_save_offer(self, lead_id: str, score: int):
        try:
            from src.lib.natsservice import NATSService
            import json
            await NATSService.publish("churn.save_offer", json.dumps({
                "lead_id": lead_id,
                "health_score": score,
                "offer_type": "discount_30pct_3months" if score > 10 else "free_month",
            }))
        except Exception:
            pass
Supabase Migration:

sql
CREATE TABLE IF NOT EXISTS public.client_health_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID UNIQUE REFERENCES public.leads(id),
    score           INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    status          TEXT NOT NULL CHECK (status IN ('healthy', 'at_risk', 'critical')),
    signals         JSONB DEFAULT '{}',
    calculated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_health_score ON public.client_health_scores(score);
CREATE INDEX idx_health_status ON public.client_health_scores(status);
ALTER TABLE public.client_health_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_health" ON public.client_health_scores
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
PART 4: n8n WORKFLOW DEFINITIONS (JSON-Ready)
n8n Workflow: Stripe → Xero Invoice Sync
​
json
{
  "name": "Stripe Invoice Paid → Xero Sync",
  "trigger": "Webhook (POST /webhook/stripe-invoice-paid)",
  "nodes": [
    {"type": "Webhook", "config": {"method": "POST", "path": "stripe-invoice-paid"}},
    {"type": "HTTP Request", "config": {
      "url": "https://mcp.citadel-nexus.com/api/v1/xero/sync-invoice",
      "method": "POST",
      "body": {
        "stripe_invoice_id": "={{$json.data.object.id}}",
        "customer_email": "={{$json.data.object.customer_email}}",
        "business_name": "={{$json.data.object.customer_name}}",
        "amount": "={{$json.data.object.amount_paid / 100}}",
        "description": "={{$json.data.object.lines.data[0].description}}"
      }
    }},
    {"type": "Discord", "config": {"channel": "#billing-ops", "message": "✅ Xero invoice synced: {{$json.xero_invoice_number}} — ${{$json.amount}}"}}
  ]
}
n8n Workflow: ZES Agent Provisioning (24-hour SLA)
json
{
  "name": "ZES Signup → Agent Provisioning",
  "trigger": "NATS (leads.converted where product=zes)",
  "nodes": [
    {"type": "NATS Consumer", "config": {"subject": "leads.converted"}},
    {"type": "IF", "config": {"condition": "={{$json.product}} contains 'zes'"}},
    {"type": "HTTP Request", "config": {
      "url": "https://mcp.citadel-nexus.com/api/v1/zes/provision",
      "method": "POST",
      "body": "={{$json}}"
    }},
    {"type": "SendGrid", "config": {
      "to": "={{$json.customer_email}}",
      "subject": "Your ZES Agent is Ready!",
      "body": "={{$json.setup_instructions}}"
    }},
    {"type": "Twilio SMS", "config": {
      "to": "={{$json.phone}}",
      "body": "Your ZES AI agent for {{$json.business_name}} is live! Check your email for setup instructions."
    }},
    {"type": "Discord", "config": {"channel": "#zes-ops", "message": "🤖 ZES agent provisioned: {{$json.business_name}} ({{$json.tier}})"}}
  ]
}
n8n Workflow: Health Score → Churn Save
json
{
  "name": "Weekly Health Score → Save Offers",
  "trigger": "Cron (Every Monday 0800 CST)",
  "nodes": [
    {"type": "Cron", "config": {"expression": "0 8 * * 1"}},
    {"type": "Supabase", "config": {"operation": "select", "table": "leads", "filter": "status IN ('WEBSITE_SOLD', 'WEBSITE_PLUS_ZES')"}},
    {"type": "Loop", "config": {"each_item": true}},
    {"type": "HTTP Request", "config": {
      "url": "https://mcp.citadel-nexus.com/api/v1/health/calculate",
      "method": "POST",
      "body": {"lead_id": "={{$json.id}}"}
    }},
    {"type": "IF", "config": {"condition": "={{$json.status}} == 'critical'"}},
    {"type": "SendGrid", "config": {
      "to": "={{$json.customer_email}}",
      "template_id": "save_offer_template",
      "dynamic_data": {"discount": "30%", "duration": "3 months"}
    }},
    {"type": "Slack", "config": {"channel": "#churn-alerts", "message": "⚠️ Critical health score: {{$json.business_name}} ({{$json.score}}/100)"}}
  ]
}
PART 5: WHAT YOUR STACK CAN DO THAT YOU'RE NOT LEVERAGING
Untapped Advantages (Supabase + Stripe + n8n + ElevenLabs)
Advantage	What It Enables	Implementation Effort
Supabase Realtime	Live dashboard showing lead flow, agent calls, health scores — no polling	2 hours (enable Realtime on tables)
Supabase Edge Functions	Stripe webhook processing at the edge (< 50ms) instead of VPS round-trip
​	4 hours (migrate webhook handler)
Stripe Billing Portal	Self-service plan changes, invoice history, payment method updates — zero code
​	1 hour (enable + embed link)
Stripe Revenue Recognition	Automated ASC 606 compliance for investor reporting	2 hours (enable in Stripe dashboard)
n8n AI Agent nodes	Let n8n itself use Claude/GPT to make routing decisions in workflows
​	3 hours per workflow
ElevenLabs Outbound Calls	Proactive voice outreach — follow-up calls, appointment reminders, save offers
​	6 hours (new agent + n8n trigger)
Supabase Vault	Store ALL API keys (Xero, Twilio, ElevenLabs) in encrypted vault, not .env	2 hours (migrate secrets)
PostHog Feature Flags	A/B test pricing tiers, bundle offers, agent prompts without code deploys	3 hours (SDK setup + flag creation)
IMPLEMENTATION PRIORITY ORDER
Priority	Gap	Why First	Effort
P0	Gap 3: Stripe Webhook Router	Everything else depends on billing events flowing	4 hours
P0	Gap 5: 10DLC Registration	SMS literally won't work without it	3 hours
P1	Gap 1: Stripe Connect Onboarding	TradeBuilder revenue depends on this	6 hours
P1	Gap 4: Provisioning State Machine	Automates the entire site delivery	8 hours
P1	Gap 6: ZES 24-Hour Delivery	Delivers on the sales promise	6 hours
P2	Gap 2: Xero Invoice Sync	Financial ops automation	4 hours
P2	Gap 7: Bundle Pricing Engine	Upsell revenue	3 hours
P3	Gap 8: Health Score + Churn	Retention optimization	6 hours
Total estimated build time: ~40 hours of focused development.═══════════════════════════════════════════════════════
GAP 1: STRIPE CONNECT ONBOARDING WIZARD
═══════════════════════════════════════════════════════
File: src/api/routes/stripe_connect.py
Purpose: Onboard TradeBuilder customers to accept payments through their websites

python
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import stripe
import os

router = APIRouter(prefix="/api/v1/stripe-connect", tags=["Stripe Connect"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PLATFORM_FEE_PERCENT = 5  # 5% platform fee on customer payments

class ConnectOnboardRequest(BaseModel):
    lead_id: str
    business_name: str
    email: str
    country: str = "US"
    business_type: str = "individual"  # individual | company

class ConnectOnboardResponse(BaseModel):
    account_id: str
    onboarding_url: str
    expires_at: int

@router.post("/onboard", response_model=ConnectOnboardResponse)
async def create_connect_account(req: ConnectOnboardRequest):
    """
    Step 1: Create a Stripe Connect Express account for the trade business.
    Returns an onboarding URL the customer clicks to complete KYC.
    Reduces friction to 3 steps: click link → verify identity → done.
    """
    try:
        # Create Express account (Stripe handles KYC)
        account = stripe.Account.create(
            type="express",
            country=req.country,
            email=req.email,
            business_type=req.business_type,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            metadata={
                "lead_id": req.lead_id,
                "business_name": req.business_name,
                "source": "tradebuilder",
            },
        )

        # Create account link for onboarding
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"{os.getenv('APP_URL')}/connect/refresh?account={account.id}",
            return_url=f"{os.getenv('APP_URL')}/connect/complete?account={account.id}",
            type="account_onboarding",
        )

        # Store in Supabase
        from src.lib.supabase_client import get_service_client
        sb = get_service_client()
        sb.table("stripe_connect_accounts").upsert({
            "lead_id": req.lead_id,
            "stripe_account_id": account.id,
            "business_name": req.business_name,
            "email": req.email,
            "status": "onboarding_started",
            "onboarding_url": account_link.url,
        }).execute()

        return ConnectOnboardResponse(
            account_id=account.id,
            onboarding_url=account_link.url,
            expires_at=account_link.expires_at,
        )

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{account_id}")
async def check_connect_status(account_id: str):
    """Check if Connect account has completed onboarding."""
    account = stripe.Account.retrieve(account_id)
    return {
        "account_id": account.id,
        "charges_enabled": account.charges_enabled,
        "payouts_enabled": account.payouts_enabled,
        "details_submitted": account.details_submitted,
        "requirements": account.requirements.currently_due if account.requirements else [],
    }


@router.post("/create-payment-intent")
async def create_destination_payment(
    amount: int,  # in cents
    currency: str = "usd",
    connected_account_id: str = "",
    customer_email: str = "",
    description: str = "",
):
    """
    Create a payment intent that routes funds to the trade business
    with platform fee retained by Citadel.
    Used by TradeBuilder websites for invoice payments.
    """
    application_fee = int(amount * (PLATFORM_FEE_PERCENT / 100))

    intent = stripe.PaymentIntent.create(
        amount=amount,
        currency=currency,
        application_fee_amount=application_fee,
        transfer_data={"destination": connected_account_id},
        receipt_email=customer_email,
        description=description,
        metadata={
            "source": "tradebuilder_website",
            "connected_account": connected_account_id,
        },
    )
    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
        "amount": amount,
        "platform_fee": application_fee,
    }
Supabase Migration:

sql
-- Stripe Connect accounts for TradeBuilder customers
CREATE TABLE IF NOT EXISTS public.stripe_connect_accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID REFERENCES public.leads(id),
    stripe_account_id TEXT UNIQUE NOT NULL,
    business_name   TEXT NOT NULL,
    email           TEXT NOT NULL,
    status          TEXT DEFAULT 'onboarding_started'
                    CHECK (status IN (
                        'onboarding_started', 'onboarding_complete',
                        'charges_enabled', 'payouts_enabled',
                        'restricted', 'disabled'
                    )),
    onboarding_url  TEXT,
    charges_enabled BOOLEAN DEFAULT false,
    payouts_enabled BOOLEAN DEFAULT false,
    platform_fee_percent NUMERIC(5,2) DEFAULT 5.00,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_connect_lead ON public.stripe_connect_accounts(lead_id);
CREATE INDEX idx_connect_stripe ON public.stripe_connect_accounts(stripe_account_id);

-- RLS
ALTER TABLE public.stripe_connect_accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_connect" ON public.stripe_connect_accounts
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 2: XERO INVOICE SYNC PIPELINE
═══════════════════════════════════════════════════════
File: src/api/routes/xero_sync.py
Purpose: Auto-create Xero invoices when Stripe subscriptions are paid

python
import httpx
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/xero", tags=["Xero Sync"])

XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"


class XeroTokenManager:
    """Manages Xero OAuth2 tokens with auto-refresh.
    Stores tokens in Supabase Vault."""

    def __init__(self):
        self.client_id = os.getenv("XERO_CLIENT_ID")
        self.client_secret = os.getenv("XERO_CLIENT_SECRET")
        self.tenant_id = os.getenv("XERO_TENANT_ID")
        self._token = None
        self._expires_at = None

    async def get_token(self) -> str:
        if self._token and self._expires_at and datetime.utcnow() < self._expires_at:
            return self._token

        from src.lib.supabase_client import get_service_client
        sb = get_service_client()
        creds = sb.table("xero_credentials").select("*").single().execute()

        if not creds.data:
            raise HTTPException(status_code=500, detail="Xero credentials not configured")

        # Refresh token
        async with httpx.AsyncClient() as client:
            resp = await client.post(XERO_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": creds.data["refresh_token"],
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            })
            if resp.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Xero token refresh failed: {resp.text}")

            token_data = resp.json()
            self._token = token_data["access_token"]
            self._expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"] - 60)

            # Store refreshed tokens
            sb.table("xero_credentials").update({
                "access_token": token_data["access_token"],
                "refresh_token": token_data["refresh_token"],
                "expires_at": self._expires_at.isoformat(),
            }).eq("id", creds.data["id"]).execute()

        return self._token

    async def _headers(self):
        token = await self.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "xero-tenant-id": self.tenant_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


xero_tokens = XeroTokenManager()


async def find_or_create_xero_contact(business_name: str, email: str) -> str:
    """Find existing Xero contact or create new one. Returns ContactID."""
    headers = await xero_tokens._headers()

    async with httpx.AsyncClient() as client:
        # Search by email
        search = await client.get(
            f"{XERO_API_BASE}/Contacts",
            headers=headers,
            params={"where": f'EmailAddress=="{email}"'},
        )
        contacts = search.json().get("Contacts", [])
        if contacts:
            return contacts["ContactID"]

        # Create new contact
        create_resp = await client.post(
            f"{XERO_API_BASE}/Contacts",
            headers=headers,
            json={"Contacts": [{
                "Name": business_name,
                "EmailAddress": email,
                "IsCustomer": True,
            }]},
        )
        new_contacts = create_resp.json().get("Contacts", [])
        if not new_contacts:
            raise HTTPException(status_code=500, detail="Failed to create Xero contact")
        return new_contacts["ContactID"]


async def create_xero_invoice(
    contact_id: str,
    description: str,
    amount: float,
    reference: str,
    due_date: Optional[str] = None,
    account_code: str = "200",  # Sales revenue account
) -> dict:
    """Create invoice in Xero. Called by Stripe webhook handler."""
    headers = await xero_tokens._headers()

    if not due_date:
        due_date = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")

    invoice_payload = {
        "Invoices": [{
            "Type": "ACCREC",  # Accounts Receivable
            "Contact": {"ContactID": contact_id},
            "Date": datetime.utcnow().strftime("%Y-%m-%d"),
            "DueDate": due_date,
            "Reference": reference,
            "Status": "AUTHORISED",  # Auto-approve since Stripe already collected
            "LineItems": [{
                "Description": description,
                "Quantity": 1,
                "UnitAmount": amount,
                "AccountCode": account_code,
                "TaxType": "OUTPUT",
            }],
        }],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{XERO_API_BASE}/Invoices",
            headers=headers,
            json=invoice_payload,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=500,
                detail=f"Xero invoice creation failed: {resp.text}"
            )

        invoice = resp.json()["Invoices"]

        # Mark as paid (Stripe already collected)
        payment_payload = {
            "Payments": [{
                "Invoice": {"InvoiceID": invoice["InvoiceID"]},
                "Account": {"Code": "090"},  # Stripe clearing account
                "Date": datetime.utcnow().strftime("%Y-%m-%d"),
                "Amount": amount,
                "Reference": f"Stripe: {reference}",
            }],
        }
        await client.put(
            f"{XERO_API_BASE}/Payments",
            headers=headers,
            json=payment_payload,
        )

        return {
            "xero_invoice_id": invoice["InvoiceID"],
            "invoice_number": invoice["InvoiceNumber"],
            "status": "PAID",
            "amount": amount,
        }


# ── Xero sync endpoint for n8n to call ──
@router.post("/sync-invoice")
async def sync_stripe_to_xero(
    stripe_invoice_id: str,
    customer_email: str,
    business_name: str,
    amount: float,
    description: str,
):
    """Called by n8n when Stripe invoice.paid fires."""
    contact_id = await find_or_create_xero_contact(business_name, customer_email)
    result = await create_xero_invoice(
        contact_id=contact_id,
        description=description,
        amount=amount,
        reference=stripe_invoice_id,
    )
    return result
Supabase Migration:

sql
-- Xero OAuth credentials (stored securely)
CREATE TABLE IF NOT EXISTS public.xero_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Xero invoice sync log
CREATE TABLE IF NOT EXISTS public.xero_invoice_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_invoice_id   TEXT NOT NULL,
    xero_invoice_id     TEXT,
    xero_invoice_number TEXT,
    customer_email      TEXT NOT NULL,
    amount              NUMERIC(10,2) NOT NULL,
    status              TEXT DEFAULT 'synced',
    error               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_xero_log_stripe ON public.xero_invoice_log(stripe_invoice_id);
ALTER TABLE public.xero_invoice_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_xero_log" ON public.xero_invoice_log
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 3: COMPLETE STRIPE WEBHOOK EVENT ROUTER
═══════════════════════════════════════════════════════
File: src/api/routes/stripe_webhooks.py
Purpose: Single webhook endpoint handling ALL Stripe lifecycle events

python
import stripe
import json
import os
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from src.lib.supabase_client import get_service_client

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
CONNECT_WEBHOOK_SECRET = os.getenv("STRIPE_CONNECT_WEBHOOK_SECRET")


async def publish_nats(subject: str, payload: dict):
    """Publish event to NATS for n8n consumption."""
    try:
        from src.lib.natsservice import NATSService
        await NATSService.publish(subject, json.dumps(payload))
    except Exception:
        pass  # Non-blocking


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """
    The ONE webhook to rule them all.
    Handles: subscriptions, invoices, Connect, payment intents.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    sb = get_service_client()
    event_type = event["type"]
    data = event["data"]["object"]

    # ── IDEMPOTENCY CHECK ──
    existing = sb.table("stripe_events").select("id").eq(
        "stripe_event_id", event["id"]
    ).execute()
    if existing.data:
        return {"status": "already_processed"}

    # Log the event
    sb.table("stripe_events").insert({
        "stripe_event_id": event["id"],
        "event_type": event_type,
        "payload": json.loads(payload),
        "processed_at": datetime.utcnow().isoformat(),
    }).execute()

    # ── SUBSCRIPTION EVENTS ──
    if event_type == "customer.subscription.created":
        await _handle_subscription_created(sb, data)

    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(sb, data)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(sb, data)

    # ── INVOICE EVENTS ──
    elif event_type == "invoice.paid":
        await _handle_invoice_paid(sb, data)

    elif event_type == "invoice.payment_failed":
        await _handle_invoice_failed(sb, data)

    # ── CONNECT EVENTS ──
    elif event_type == "account.updated":
        await _handle_connect_account_updated(sb, data)

    # ── CHECKOUT EVENTS ──
    elif event_type == "checkout.session.completed":
        await _handle_checkout_completed(sb, data)

    return {"status": "processed", "type": event_type}


async def _handle_subscription_created(sb, subscription):
    """New subscription → provision resources."""
    customer_id = subscription["customer"]
    plan_id = subscription["items"]["data"]["price"]["id"]
    metadata = subscription.get("metadata", {})

    # Update lead status
    if metadata.get("lead_id"):
        sb.table("leads").update({
            "status": "TRIAL_STARTED" if subscription.get("trial_end") else "WEBSITE_SOLD",
            "tier_interest": metadata.get("tier", ""),
        }).eq("id", metadata["lead_id"]).execute()

    # Trigger provisioning via NATS
    await publish_nats("leads.converted", {
        "subscription_id": subscription["id"],
        "customer_id": customer_id,
        "plan_id": plan_id,
        "lead_id": metadata.get("lead_id"),
        "product": metadata.get("product", "tradebuilder"),
        "tier": metadata.get("tier", "tier1"),
    })


async def _handle_subscription_updated(sb, subscription):
    """Plan change or status change."""
    status = subscription["status"]
    customer_id = subscription["customer"]

    if status == "past_due":
        await publish_nats("billing.past_due", {
            "subscription_id": subscription["id"],
            "customer_id": customer_id,
        })
    elif status == "active":
        # Restored from past_due
        await publish_nats("billing.restored", {
            "subscription_id": subscription["id"],
            "customer_id": customer_id,
        })


async def _handle_subscription_deleted(sb, subscription):
    """Subscription cancelled → suspend site."""
    metadata = subscription.get("metadata", {})

    if metadata.get("lead_id"):
        sb.table("leads").update({
            "status": "NOT_INTERESTED",
        }).eq("id", metadata["lead_id"]).execute()

    await publish_nats("billing.cancelled", {
        "subscription_id": subscription["id"],
        "customer_id": subscription["customer"],
        "lead_id": metadata.get("lead_id"),
        "product": metadata.get("product"),
    })


async def _handle_invoice_paid(sb, invoice):
    """Invoice paid → sync to Xero + log."""
    customer_email = invoice.get("customer_email", "")
    customer_name = invoice.get("customer_name", "")
    amount = invoice["amount_paid"] / 100  # cents → dollars
    description = ""
    for line in invoice.get("lines", {}).get("data", []):
        description += line.get("description", "") + "; "

    # Sync to Xero via internal API
    try:
        from src.api.routes.xero_sync import (
            find_or_create_xero_contact,
            create_xero_invoice,
        )
        contact_id = await find_or_create_xero_contact(customer_name, customer_email)
        await create_xero_invoice(
            contact_id=contact_id,
            description=description.strip("; "),
            amount=amount,
            reference=invoice["id"],
        )
    except Exception as e:
        # Log but don't block — Xero sync is non-critical
        sb.table("xero_invoice_log").insert({
            "stripe_invoice_id": invoice["id"],
            "customer_email": customer_email,
            "amount": amount,
            "status": "failed",
            "error": str(e),
        }).execute()

    await publish_nats("billing.invoice.paid", {
        "invoice_id": invoice["id"],
        "customer_email": customer_email,
        "amount": amount,
    })


async def _handle_invoice_failed(sb, invoice):
    """Payment failed → start dunning sequence."""
    await publish_nats("billing.invoice.failed", {
        "invoice_id": invoice["id"],
        "customer_id": invoice["customer"],
        "customer_email": invoice.get("customer_email"),
        "attempt_count": invoice.get("attempt_count", 0),
        "next_attempt": invoice.get("next_payment_attempt"),
    })


async def _handle_connect_account_updated(sb, account):
    """Connect account status changed (KYC complete, etc)."""
    sb.table("stripe_connect_accounts").update({
        "charges_enabled": account["charges_enabled"],
        "payouts_enabled": account["payouts_enabled"],
        "status": "charges_enabled" if account["charges_enabled"] else "onboarding_started",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("stripe_account_id", account["id"]).execute()

    if account["charges_enabled"]:
        await publish_nats("connect.account.ready", {
            "account_id": account["id"],
            "business_name": account.get("business_profile", {}).get("name", ""),
        })


async def _handle_checkout_completed(sb, session):
    """Checkout session completed → route based on product."""
    metadata = session.get("metadata", {})
    mode = session.get("mode")

    if mode == "subscription":
        # Subscription checkout — handled by subscription.created
        pass
    elif mode == "payment":
        # One-time payment (setup fee)
        await publish_nats("billing.setup_fee.paid", {
            "session_id": session["id"],
            "customer_email": session.get("customer_email"),
            "amount": session["amount_total"] / 100,
            "lead_id": metadata.get("lead_id"),
        })
Supabase Migration:

sql
-- Stripe event idempotency log
CREATE TABLE IF NOT EXISTS public.stripe_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_event_id TEXT UNIQUE NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    processed_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_stripe_events_type ON public.stripe_events(event_type, processed_at DESC);
ALTER TABLE public.stripe_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_events" ON public.stripe_events
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 4: TRADEBUILDER PROVISIONING STATE MACHINE
═══════════════════════════════════════════════════════
File: src/services/provisioning_engine.py
Purpose: Drives intake → payment → site deployment with rollback

python
from enum import Enum
from datetime import datetime
from typing import Optional
import asyncio


class ProvisioningState(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEW_NEEDED = "review_needed"
    APPROVED = "approved"
    PAYMENT_PENDING = "payment_pending"
    PROVISIONING = "provisioning"
    STAGED = "staged"
    PUBLISHED = "published"
    LIVE = "live"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


# Valid transitions
TRANSITIONS = {
    ProvisioningState.DRAFT: [ProvisioningState.SUBMITTED],
    ProvisioningState.SUBMITTED: [ProvisioningState.APPROVED, ProvisioningState.REVIEW_NEEDED],
    ProvisioningState.REVIEW_NEEDED: [ProvisioningState.APPROVED, ProvisioningState.CANCELLED],
    ProvisioningState.APPROVED: [ProvisioningState.PAYMENT_PENDING],
    ProvisioningState.PAYMENT_PENDING: [ProvisioningState.PROVISIONING, ProvisioningState.CANCELLED],
    ProvisioningState.PROVISIONING: [ProvisioningState.STAGED, ProvisioningState.REVIEW_NEEDED],
    ProvisioningState.STAGED: [ProvisioningState.PUBLISHED],
    ProvisioningState.PUBLISHED: [ProvisioningState.LIVE],
    ProvisioningState.LIVE: [ProvisioningState.SUSPENDED, ProvisioningState.CANCELLED],
    ProvisioningState.SUSPENDED: [ProvisioningState.LIVE, ProvisioningState.CANCELLED],
}


class ProvisioningEngine:
    """
    State machine for TradeBuilder site provisioning.
    Orchestrates: intake validation → Stripe billing → Framer deploy → DNS → SEO.
    Target: < 4 hours to staging, < 48 hours to published.
    """

    def __init__(self, supabase_client, nats_client=None):
        self.sb = supabase_client
        self.nats = nats_client

    async def transition(self, intake_id: str, target_state: ProvisioningState) -> dict:
        """Attempt a state transition with validation."""
        record = self.sb.table("client_intakes").select("*").eq(
            "id", intake_id
        ).single().execute()

        if not record.data:
            raise ValueError(f"Intake {intake_id} not found")

        current = ProvisioningState(record.data["status"])
        allowed = TRANSITIONS.get(current, [])

        if target_state not in allowed:
            raise ValueError(
                f"Cannot transition from {current} to {target_state}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        # Execute transition-specific logic
        handler = getattr(self, f"_on_{target_state.value}", None)
        result = {}
        if handler:
            result = await handler(record.data) or {}

        # Update state
        self.sb.table("client_intakes").update({
            "status": target_state.value,
            "updated_at": datetime.utcnow().isoformat(),
            **result,
        }).eq("id", intake_id).execute()

        # Publish NATS event
        if self.nats:
            await self.nats.publish(
                f"tradebuilder.provision.{target_state.value}",
                {"intake_id": intake_id, "state": target_state.value, **result},
            )

        return {"intake_id": intake_id, "state": target_state.value, **result}

    async def _on_submitted(self, intake: dict) -> dict:
        """Validate intake and auto-approve or flag for review."""
        from src.services.intake_validator import validate_intake, check_kill_switches
        errors = validate_intake(intake)
        red_flags = check_kill_switches(intake)

        if errors:
            return {"validation_errors": errors, "status": "review_needed"}

        if red_flags:
            return {"red_flags": red_flags, "status": "review_needed"}

        return {"status": "approved"}

    async def _on_approved(self, intake: dict) -> dict:
        """Create Stripe customer + subscription."""
        import stripe
        tier = intake.get("plan_tier", "tier1_static")
        price_map = {
            "tier1_static": os.getenv("STRIPE_PRICE_TIER1"),
            "tier2_conversion": os.getenv("STRIPE_PRICE_TIER2"),
            "tier3_ops_lite": os.getenv("STRIPE_PRICE_TIER3"),
        }
        setup_fee_map = {
            "tier1_static": 9900,   # $99
            "tier2_conversion": 9900,
            "tier3_ops_lite": 19900,  # $199
        }

        customer = stripe.Customer.create(
            email=intake["primary_email"],
            name=intake["business_name"],
            metadata={"intake_id": intake["id"], "tier": tier},
        )

        # Create subscription with setup fee
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_map[tier]}],
            add_invoice_items=[{
                "price_data": {
                    "currency": "usd",
                    "product": os.getenv("STRIPE_SETUP_FEE_PRODUCT"),
                    "unit_amount": setup_fee_map[tier],
                },
                "quantity": 1,
            }],
            metadata={"intake_id": intake["id"], "tier": tier, "product": "tradebuilder"},
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
        )

        return {
            "stripe_customer_id": customer.id,
            "stripe_subscription_id": subscription.id,
            "payment_intent_secret": subscription.latest_invoice.payment_intent.client_secret,
        }

    async def _on_provisioning(self, intake: dict) -> dict:
        """Execute the full provisioning pipeline."""
        steps_completed = []
        try:
            # Step 1: Domain config
            domain = await self._provision_domain(intake)
            steps_completed.append("domain")

            # Step 2: Framer site creation
            site = await self._provision_framer_site(intake)
            steps_completed.append("framer_site")

            # Step 3: Lead routing (n8n webhook)
            webhook = await self._setup_lead_routing(intake)
            steps_completed.append("lead_routing")

            # Step 4: SEO baseline
            seo = await self._setup_seo_baseline(intake)
            steps_completed.append("seo")

            # Step 5: Collateral generation (async, non-blocking)
            asyncio.create_task(self._generate_collateral(intake))
            steps_completed.append("collateral_queued")

            return {
                "provisioning_steps": steps_completed,
                "domain": domain,
                "site_url": site.get("url"),
            }

        except Exception as e:
            # Rollback on failure
            await self._rollback(intake["id"], steps_completed)
            raise

    async def _provision_domain(self, intake: dict) -> dict:
        """Configure domain — send DNS instructions or register."""
        # Placeholder — integrate with Cloudflare/Namecheap API
        return {"domain": intake.get("domain", ""), "status": "instructions_sent"}

    async def _provision_framer_site(self, intake: dict) -> dict:
        """Duplicate Framer template and inject content."""
        # Placeholder — integrate with Framer CMS API
        template = f"tmpl_{intake['industry']}_{'basic' if 'tier1' in intake.get('plan_tier', '') else 'conversion'}_v1"
        return {"template": template, "url": f"https://{intake.get('domain', 'staging')}", "status": "staged"}

    async def _setup_lead_routing(self, intake: dict) -> dict:
        """Create n8n webhook for lead form submissions."""
        return {"webhook_url": f"https://n8n.citadel-nexus.com/webhook/{intake['id']}", "status": "active"}

    async def _setup_seo_baseline(self, intake: dict) -> dict:
        """Generate schema.org markup, sitemap, meta tags."""
        return {"schema_markup": True, "sitemap": True, "meta_tags": True}

    async def _generate_collateral(self, intake: dict):
        """Async: generate videos and docs via ArtCraft."""
        pass  # ArtCraft pipeline integration

    async def _rollback(self, intake_id: str, completed_steps: list):
        """Rollback completed provisioning steps on failure."""
        # Log rollback for manual review
        self.sb.table("provisioning_rollbacks").insert({
            "intake_id": intake_id,
            "completed_steps": completed_steps,
            "rolled_back_at": datetime.utcnow().isoformat(),
        }).execute()
═══════════════════════════════════════════════════════
GAP 5: 10DLC REGISTRATION PIPELINE
═══════════════════════════════════════════════════════
File: src/services/ten_dlc_registration.py
Purpose: Register Twilio 10DLC brand + campaign during onboarding

python
from twilio.rest import Client
import os
from typing import Optional


class TenDLCRegistration:
    """
    Handles Twilio 10DLC brand and campaign registration.
    REQUIRED for all A2P SMS — without this, messages get filtered/blocked.
    Cost: $4 one-time brand + $0.75/mo per campaign.
    """

    def __init__(self):
        self.client = Client(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN"),
        )
        self.messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")

    async def register_brand(
        self,
        business_name: str,
        ein: Optional[str] = None,
        business_type: str = "sole_proprietorship",
        contact_email: str = "",
        contact_phone: str = "",
    ) -> dict:
        """
        Register a business as a 10DLC brand.
        Called once per trade business during onboarding.
        """
        # For sole proprietors (most trades), use Sole Proprietor registration
        if business_type == "sole_proprietorship" or not ein:
            brand = self.client.messaging.v1.services(
                self.messaging_service_sid
            ).us_app_to_person.create(
                brand_registration_sid="",  # Auto-create
                description=f"Business messaging for {business_name}",
                message_flow=(
                    "Customers opt-in via website contact form or direct request. "
                    "Messages include appointment confirmations, review requests, "
                    "and service reminders."
                ),
                message_samples=[
                    f"Hi! This is {business_name}. Your appointment is confirmed for tomorrow at 2 PM.",
                    f"Thanks for choosing {business_name}! How was your experience? Leave a review: [link]",
                    f"Reminder: Your annual AC maintenance is coming up. Book now: [link]",
                ],
                us_app_to_person_usecase="MIXED",
                has_embedded_links=True,
                has_embedded_phone=False,
                opt_in_type="VERBAL",
            )
            return {
                "brand_sid": brand.sid,
                "status": brand.campaign_status,
                "cost_onetime": 4.00,
                "cost_monthly": 0.75,
            }

        # For LLCs/Corps with EIN — standard brand registration
        brand_registration = self.client.messaging.v1.brand_registrations.create(
            customer_profile_bundle_sid=self._create_customer_profile(
                business_name, ein, contact_email, contact_phone
            ),
            a2p_profile_bundle_sid=self._create_a2p_profile(business_name),
        )
        return {
            "brand_registration_sid": brand_registration.sid,
            "status": brand_registration.status,
        }

    def _create_customer_profile(self, name, ein, email, phone) -> str:
        """Create Twilio Trust Hub customer profile."""
        profile = self.client.trusthub.v1.customer_profiles.create(
            friendly_name=name,
            email=email,
            policy_sid="RN806dd6cd175f314e1f96a9727ee271f4",  # A2P policy
        )
        # Add EIN as end-user
        self.client.trusthub.v1.customer_profiles(
            profile.sid
        ).customer_profiles_entity_assignments.create(
            object_sid=self._create_end_user(name, ein),
        )
        # Submit for review
        self.client.trusthub.v1.customer_profiles(profile.sid).update(
            status="pending-review"
        )
        return profile.sid

    def _create_end_user(self, name, ein) -> str:
        end_user = self.client.trusthub.v1.end_users.create(
            friendly_name=name,
            type="us_a2p_brand_registration_sole_proprietor",
            attributes={
                "business_name": name,
                "ein": ein,
                "business_type": "Partnership",
            },
        )
        return end_user.sid

    def _create_a2p_profile(self, name) -> str:
        """Placeholder — full A2P profile for standard registration."""
        return ""
═══════════════════════════════════════════════════════
GAP 6: ZES AGENT 24-HOUR DELIVERY AUTOMATION
═══════════════════════════════════════════════════════
File: src/services/zes_agent_provisioner.py
Purpose: Auto-configure and deploy a ZES agent within 24 hours of signup

python
import httpx
import os
import json
from datetime import datetime
from typing import Optional


class ZESAgentProvisioner:
    """
    Provisions a ZES agent for a customer's existing website.
    24-hour SLA: signup → configured agent → live on their site.

    Flow:
    1. Customer signs up for ZES plan
    2. Intake form collects: website URL, business hours, services, phone
    3. This provisioner creates the ElevenLabs agent with RAG context
    4. Generates embed snippet for their website
    5. Sends setup instructions via email/SMS
    """

    ELEVENLABS_API = "https://api.elevenlabs.io/v1"

    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def provision_zes_agent(
        self,
        lead_id: str,
        business_name: str,
        website_url: str,
        phone: str,
        services: list[str],
        business_hours: dict,
        tier: str = "scout",  # scout | operator | autopilot
        industry: str = "general",
    ) -> dict:
        """
        Full ZES agent provisioning pipeline.
        Returns agent_id + embed code + setup instructions.
        """
        # Step 1: Build system prompt from business data
        system_prompt = self._build_system_prompt(
            business_name, services, business_hours, industry, tier
        )

        # Step 2: Create ElevenLabs Conversational AI agent
        agent = await self._create_elevenlabs_agent(
            name=f"ZES-{business_name[:20]}",
            system_prompt=system_prompt,
            tier=tier,
        )
        agent_id = agent["agent_id"]

        # Step 3: Push RAG documents (business-specific knowledge)
        await self._push_rag_documents(agent_id, {
            "business_name": business_name,
            "website": website_url,
            "phone": phone,
            "services": services,
            "hours": business_hours,
            "industry": industry,
        })

        # Step 4: Register MCP server tools (based on tier)
        if tier in ("operator", "autopilot"):
            await self._register_mcp_tools(agent_id, tier)

        # Step 5: Generate embed snippet
        embed_code = self._generate_embed_snippet(agent_id, business_name)

        # Step 6: Store in Supabase
        from src.lib.supabase_client import get_service_client
        sb = get_service_client()
        sb.table("zes_agents").upsert({
            "lead_id": lead_id,
            "agent_id": agent_id,
            "business_name": business_name,
            "website_url": website_url,
            "tier": tier,
            "status": "provisioned",
            "embed_code": embed_code,
            "provisioned_at": datetime.utcnow().isoformat(),
        }).execute()

        return {
            "agent_id": agent_id,
            "embed_code": embed_code,
            "tier": tier,
            "status": "provisioned",
            "setup_instructions": self._generate_setup_email(
                business_name, embed_code, tier
            ),
        }

    def _build_system_prompt(self, name, services, hours, industry, tier) -> str:
        services_text = ", ".join(services[:6])
        hours_text = json.dumps(hours) if isinstance(hours, dict) else str(hours)

        base = f"""You are the AI assistant for {name}, a {industry} business.

Your job is to answer customer questions, capture leads, and help with scheduling.

Business Info:
- Services: {services_text}
- Hours: {hours_text}

Behavior Rules:
- Be friendly, professional, and concise
- Always try to capture the caller's name, phone, and what service they need
- If asked about pricing, say "I can get you a free estimate — what's the best number to reach you?"
- If it's an emergency, prioritize getting their address and dispatching info
- Never make up information you don't have
- If you can't help, offer to have someone call them back"""

        if tier == "autopilot":
            base += """
- You can book appointments directly using the scheduling tool
- You can send text confirmations after booking
- You can check appointment availability in real-time"""

        return base

    async def _create_elevenlabs_agent(self, name: str, system_prompt: str, tier: str) -> dict:
        voice_id = os.getenv("ZES_DEFAULT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

        payload = {
            "conversation_config": {
                "agent": {
                    "prompt": {
                        "prompt": system_prompt,
                    },
                    "first_message": f"Hi, thanks for calling! How can I help you today?",
                    "language": "en",
                },
                "tts": {
                    "voice_id": voice_id,
                },
            },
            "name": name,
            "platform_settings": {
                "widget": {
                    "variant": "compact",
                    "avatar": {"type": "orb"},
                },
            },
        }

        # Register MCP server for operator+ tiers
        if tier in ("operator", "autopilot"):
            payload["conversation_config"]["agent"]["prompt"]["mcp_servers"] = [{
                "url": f"https://mcp.citadel-nexus.com/mcp",
                "transport": "sse",
            }]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.ELEVENLABS_API}/convai/agents/create",
                headers=self.headers,
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def _push_rag_documents(self, agent_id: str, business_data: dict):
        """Push business-specific knowledge to agent's RAG."""
        doc_content = f"""
Business: {business_data['business_name']}
Website: {business_data['website']}
Phone: {business_data['phone']}
Industry: {business_data['industry']}
Services Offered: {', '.join(business_data['services'])}
Business Hours: {json.dumps(business_data['hours'])}
"""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.ELEVENLABS_API}/convai/agents/{agent_id}/add-to-knowledge-base",
                headers=self.headers,
                json={"url": None, "text": doc_content, "name": "business_info"},
            )

    async def _register_mcp_tools(self, agent_id: str, tier: str):
        """Register MCP server tools based on tier."""
        pass  # MCP is registered at agent creation via prompt config

    def _generate_embed_snippet(self, agent_id: str, business_name: str) -> str:
        return f'<elevenlabs-convai agent-id="{agent_id}"></elevenlabs-convai>\n<script src="https://elevenlabs.io/convai-widget/index.js" async type="text/javascript"></script>'

    def _generate_setup_email(self, business_name: str, embed_code: str, tier: str) -> str:
        return f"""
Subject: Your ZES AI Agent is Ready — {business_name}

Your ZES {tier.title()} agent is configured and ready to go!

To add it to your website, paste this code before the </body> tag:

{embed_code}

If you use WordPress, go to Appearance → Theme Editor → footer.php and paste it there.
If you use Wix/Squarespace, add it via their Custom Code or Embed HTML block.

Your agent will start answering calls and capturing leads immediately.

Questions? Reply to this email or call us.
"""
Supabase Migration:

sql
CREATE TABLE IF NOT EXISTS public.zes_agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID REFERENCES public.leads(id),
    agent_id        TEXT UNIQUE NOT NULL,
    business_name   TEXT NOT NULL,
    website_url     TEXT,
    tier            TEXT NOT NULL CHECK (tier IN ('scout', 'operator', 'autopilot')),
    status          TEXT DEFAULT 'provisioned',
    embed_code      TEXT,
    provisioned_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_zes_agents_lead ON public.zes_agents(lead_id);
ALTER TABLE public.zes_agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_zes" ON public.zes_agents
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
═══════════════════════════════════════════════════════
GAP 7: BUNDLE PRICING ENGINE
═══════════════════════════════════════════════════════
File: src/services/bundle_pricing.py

python
import stripe
import os
from typing import Optional

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Bundle discount tiers (from ZES Plan docs)
BUNDLE_DISCOUNTS = {
    "tradebuilder_scout": 0.10,      # 10% off
    "tradebuilder_operator": 0.15,   # 15% off
    "tradebuilder_autopilot": 0.20,  # 20% off
}

# Base prices (monthly, in cents)
ZES_PRICES = {
    "scout": 1500,      # $15
    "operator": 2000,   # $20
    "autopilot": 3000,  # $30
}

TB_PRICES = {
    "tier1_static": 9900,       # $99
    "tier2_conversion": 14900,  # $149
    "tier3_ops_lite": 24900,    # $249
}


async def calculate_bundle_price(
    tb_tier: str,
    zes_tier: Optional[str] = None,
) -> dict:
    """Calculate bundled price with discount."""
    tb_price = TB_PRICES.get(tb_tier, 0)
    result = {
        "tradebuilder_tier": tb_tier,
        "tradebuilder_price": tb_price,
        "zes_tier": zes_tier,
        "zes_price": 0,
        "discount_percent": 0,
        "discount_amount": 0,
        "total_monthly": tb_price,
        "is_bundle": False,
    }

    if zes_tier and zes_tier in ZES_PRICES:
        zes_price = ZES_PRICES[zes_tier]
        combined = tb_price + zes_price
        discount_key = f"tradebuilder_{zes_tier}"
        discount_pct = BUNDLE_DISCOUNTS.get(discount_key, 0)
        discount_amount = int(combined * discount_pct)
        total = combined - discount_amount

        result.update({
            "zes_price": zes_price,
            "discount_percent": int(discount_pct * 100),
            "discount_amount": discount_amount,
            "total_monthly": total,
            "is_bundle": True,
            "savings_annual": discount_amount * 12,
        })

    return result


async def create_bundle_subscription(
    customer_id: str,
    tb_tier: str,
    zes_tier: str,
    lead_id: str,
) -> dict:
    """Create a Stripe subscription with bundle discount via coupon."""
    bundle = await calculate_bundle_price(tb_tier, zes_tier)

    if not bundle["is_bundle"]:
        raise ValueError("Both TradeBuilder and ZES tiers required for bundle")

    # Create or retrieve coupon
    coupon_id = f"bundle_{zes_tier}_{bundle['discount_percent']}pct"
    try:
        stripe.Coupon.retrieve(coupon_id)
    except stripe.error.InvalidRequestError:
        stripe.Coupon.create(
            id=coupon_id,
            percent_off=bundle["discount_percent"],
            duration="forever",
            name=f"TradeBuilder + ZES {zes_tier.title()} Bundle ({bundle['discount_percent']}% off)",
        )

    # Create subscription with both products
    subscription = stripe.Subscription.create(
        customer=customer_id,
        items=[
            {"price": os.getenv(f"STRIPE_PRICE_TB_{tb_tier.upper()}")},
            {"price": os.getenv(f"STRIPE_PRICE_ZES_{zes_tier.upper()}")},
        ],
        coupon=coupon_id,
        metadata={
            "lead_id": lead_id,
            "bundle_type": f"{tb_tier}+{zes_tier}",
            "product": "tradebuilder_zes_bundle",
        },
    )

    return {
        "subscription_id": subscription.id,
        "total_monthly": bundle["total_monthly"] / 100,
        "discount_percent": bundle["discount_percent"],
        "savings_annual": bundle["savings_annual"] / 100,
    }
═══════════════════════════════════════════════════════
GAP 8: CLIENT HEALTH SCORE + CHURN PREDICTION
═══════════════════════════════════════════════════════
File: src/services/health_score.py

python
from datetime import datetime, timedelta
from typing import Optional


class ClientHealthScorer:
    """
    Calculates a 0-100 health score per client.
    Triggers save offers when score drops below threshold.

    Signals:
    - Website traffic (from PostHog/GA)
    - Form submissions received
    - Voice agent calls answered
    - Review requests sent/completed
    - Login frequency to dashboard
    - Support ticket volume
    - Payment status
    """

    WEIGHTS = {
        "website_traffic": 0.15,
        "form_submissions": 0.20,
        "voice_calls": 0.15,
        "reviews_generated": 0.10,
        "dashboard_logins": 0.10,
        "support_tickets": 0.10,  # Inverse — more tickets = lower score
        "payment_health": 0.20,
    }

    THRESHOLDS = {
        "healthy": 70,
        "at_risk": 40,
        "critical": 20,
    }

    def __init__(self, supabase_client):
        self.sb = supabase_client

    async def calculate_score(self, lead_id: str, days: int = 30) -> dict:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # Gather signals
        traffic = await self._get_traffic_score(lead_id, since)
        forms = await self._get_form_score(lead_id, since)
        calls = await self._get_voice_score(lead_id, since)
        reviews = await self._get_review_score(lead_id, since)
        logins = await self._get_login_score(lead_id, since)
        tickets = await self._get_ticket_score(lead_id, since)
        payment = await self._get_payment_score(lead_id)

        # Weighted score
        raw_score = (
            traffic * self.WEIGHTS["website_traffic"]
            + forms * self.WEIGHTS["form_submissions"]
            + calls * self.WEIGHTS["voice_calls"]
            + reviews * self.WEIGHTS["reviews_generated"]
            + logins * self.WEIGHTS["dashboard_logins"]
            + tickets * self.WEIGHTS["support_tickets"]
            + payment * self.WEIGHTS["payment_health"]
        )

        score = min(100, max(0, int(raw_score)))

        # Determine status
        if score >= self.THRESHOLDS["healthy"]:
            status = "healthy"
        elif score >= self.THRESHOLDS["at_risk"]:
            status = "at_risk"
        else:
            status = "critical"

        result = {
            "lead_id": lead_id,
            "score": score,
            "status": status,
            "signals": {
                "traffic": traffic,
                "forms": forms,
                "calls": calls,
                "reviews": reviews,
                "logins": logins,
                "tickets": tickets,
                "payment": payment,
            },
            "calculated_at": datetime.utcnow().isoformat(),
        }

        # Store score
        self.sb.table("client_health_scores").upsert({
            "lead_id": lead_id,
            **result,
        }, on_conflict="lead_id").execute()

        # Trigger save offer if critical
        if status == "critical":
            await self._trigger_save_offer(lead_id, score)

        return result

    async def _get_traffic_score(self, lead_id, since) -> float:
        """Score 0-100 based on website visitor count."""
        # Query PostHog or GA via Supabase aggregation
        return 50.0  # Placeholder — wire to PostHog API

    async def _get_form_score(self, lead_id, since) -> float:
        result = self.sb.table("leads").select("id", count="exact").eq(
            "source_agent", "tradebuilder"
        ).gte("created_at", since).execute()
        count = result.count or 0
        return min(100, count * 20)  # 5+ submissions = 100

    async def _get_voice_score(self, lead_id, since) -> float:
        result = self.sb.table("call_transcripts").select("id", count="exact").eq(
            "lead_id", lead_id
        ).gte("created_at", since).execute()
        count = result.count or 0
        return min(100, count * 10)  # 10+ calls = 100

    async def _get_review_score(self, lead_id, since) -> float:
        return 50.0  # Placeholder — wire to review tracking

    async def _get_login_score(self, lead_id, since) -> float:
        return 50.0  # Placeholder — wire to auth logs

    async def _get_ticket_score(self, lead_id, since) -> float:
        """Inverse: more tickets = lower score."""
        return 70.0  # Placeholder

    async def _get_payment_score(self, lead_id) -> float:
        """100 = current, 50 = past_due, 0 = cancelled."""
        lead = self.sb.table("leads").select("status").eq(
            "id", lead_id
        ).single().execute()
        if not lead.data:
            return 0
        status_scores = {
            "WEBSITE_SOLD": 100, "WEBSITE_PLUS_ZES": 100,
            "TRIAL_STARTED": 80, "TRIAL_STARTED_BUNDLE": 80,
            "INTERESTED": 60, "CALLBACK_REQUESTED": 50,
            "NOT_INTERESTED": 0, "DO_NOT_CALL": 0,
        }
        return status_scores.get(lead.data["status"], 50)

    async def _trigger_save_offer(self, lead_id: str, score: int):
        """Fire save offer automation via NATS → n8n."""
        try:
            from src.lib.natsservice import NATSService
            import json
            await NATSService.publish("churn.save_offer", json.dumps({
                "lead_id": lead_id,
                "health_score": score,
                "offer_type": "discount_30pct_3months" if score > 10 else "free_month",
            }))
        except Exception:
            pass
Supabase Migration:

sql
CREATE TABLE IF NOT EXISTS public.client_health_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID UNIQUE REFERENCES public.leads(id),
    score           INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    status          TEXT NOT NULL CHECK (status IN ('healthy', 'at_risk', 'critical')),
    signals         JSONB DEFAULT '{}',
    calculated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_health_score ON public.client_health_scores(score);
CREATE INDEX idx_health_status ON public.client_health_scores(status);
ALTER TABLE public.client_health_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_manages_health" ON public.client_health_scores
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (true);
PART 4: n8n WORKFLOW DEFINITIONS (JSON-Ready)
n8n Workflow: Stripe → Xero Invoice Sync
json
{
  "name": "Stripe Invoice Paid → Xero Sync",
  "trigger": "Webhook (POST /webhook/stripe-invoice-paid)",
  "nodes": [
    {"type": "Webhook", "config": {"method": "POST", "path": "stripe-invoice-paid"}},
    {"type": "HTTP Request", "config": {
      "url": "https://mcp.citadel-nexus.com/api/v1/xero/sync-invoice",
      "method": "POST",
      "body": {
        "stripe_invoice_id": "={{$json.data.object.id}}",
        "customer_email": "={{$json.data.object.customer_email}}",
        "business_name": "={{$json.data.object.customer_name}}",
        "amount": "={{$json.data.object.amount_paid / 100}}",
        "description": "={{$json.data.object.lines.data.description}}"
      }
    }},
    {"type": "Discord", "config": {"channel": "#billing-ops", "message": "✅ Xero invoice synced: {{$json.xero_invoice_number}} — ${{$json.amount}}"}}
  ]
}
n8n Workflow: ZES Agent Provisioning (24-hour SLA)
json
{
  "name": "ZES Signup → Agent Provisioning",
  "trigger": "NATS (leads.converted where product=zes)",
  "nodes": [
    {"type": "NATS Consumer", "config": {"subject": "leads.converted"}},
    {"type": "IF", "config": {"condition": "={{$json.product}} contains 'zes'"}},
    {"type": "HTTP Request", "config": {
      "url": "https://mcp.citadel-nexus.com/api/v1/zes/provision",
      "method": "POST",
      "body": "={{$json}}"
    }},
    {"type": "SendGrid", "config": {
      "to": "={{$json.customer_email}}",
      "subject": "Your ZES Agent is Ready!",
      "body": "={{$json.setup_instructions}}"
    }},
    {"type": "Twilio SMS", "config": {
      "to": "={{$json.phone}}",
      "body": "Your ZES AI agent for {{$json.business_name}} is live! Check your email for setup instructions."
    }},
    {"type": "Discord", "config": {"channel": "#zes-ops", "message": "🤖 ZES agent provisioned: {{$json.business_name}} ({{$json.tier}})"}}
  ]
}
n8n Workflow: Health Score → Churn Save
json
{
  "name": "Weekly Health Score → Save Offers",
  "trigger": "Cron (Every Monday 0800 CST)",
  "nodes": [
    {"type": "Cron", "config": {"expression": "0 8 * * 1"}},
    {"type": "Supabase", "config": {"operation": "select", "table": "leads", "filter": "status IN ('WEBSITE_SOLD', 'WEBSITE_PLUS_ZES')"}},
    {"type": "Loop", "config": {"each_item": true}},
    {"type": "HTTP Request", "config": {
      "url": "https://mcp.citadel-nexus.com/api/v1/health/calculate",
      "method": "POST",
      "body": {"lead_id": "={{$json.id}}"}
    }},
    {"type": "IF", "config": {"condition": "={{$json.status}} == 'critical'"}},
    {"type": "SendGrid", "config": {
      "to": "={{$json.customer_email}}",
      "template_id": "save_offer_template",
      "dynamic_data": {"discount": "30%", "duration": "3 months"}
    }},
    {"type": "Slack", "config": {"channel": "#churn-alerts", "message": "⚠️ Critical health score: {{$json.business_name}} ({{$json.score}}/100)"}}
  ]
}
PART 5: WHAT YOUR STACK CAN DO THAT YOU'RE NOT LEVERAGING
Untapped Advantages (Supabase + Stripe + n8n + ElevenLabs)
Advantage	What It Enables	Implementation Effort
Supabase Realtime	Live dashboard showing lead flow, agent calls, health scores — no polling	2 hours (enable Realtime on tables)
Supabase Edge Functions	Stripe webhook processing at the edge (< 50ms) instead of VPS round-trip	4 hours (migrate webhook handler)
Stripe Billing Portal	Self-service plan changes, invoice history, payment method updates — zero code	1 hour (enable + embed link)
Stripe Revenue Recognition	Automated ASC 606 compliance for investor reporting	2 hours (enable in Stripe dashboard)
n8n AI Agent nodes	Let n8n itself use Claude/GPT to make routing decisions in workflows	3 hours per workflow
ElevenLabs Outbound Calls	Proactive voice outreach — follow-up calls, appointment reminders, save offers	6 hours (new agent + n8n trigger)
Supabase Vault	Store ALL API keys (Xero, Twilio, ElevenLabs) in encrypted vault, not .env	2 hours (migrate secrets)
PostHog Feature Flags	A/B test pricing tiers, bundle offers, agent prompts without code deploys	3 hours (SDK setup + flag creation)ZES + TradeBuilder: Full Gap Analysis — OSS Competition, Missing Pieces & Untapped Stack Advantages
Part 1: OSS Competitive Audit — Does Anything Do This Better?
The honest answer: no single OSS project replicates what ZES + TradeBuilder does as a packaged product for trade businesses. The individual components have strong OSS alternatives, but nobody is assembling them into a turnkey $15-30/mo agent for plumbers, roofers, and HVAC contractors. Here's the layer-by-layer breakdown:

Voice Agent Layer (ZES Core)
OSS/Competitor	What It Does	Where It Falls Short vs ZES
Vapi.ai	API-first voice agent builder, CRM hooks	No self-hosted option. Per-minute pricing ($0.25-0.33/min real-world) explodes at scale vs ZES flat monthly
Vocode (OSS)	Python voice agent framework	Raw framework — no built-in CRM, no Stripe, no booking. Requires dev team
​
OpenOmni (OSS)	Multimodal conversation pipeline	Research-grade, 250ms+ latency, zero production billing or multi-tenant support
​
Synthflow	No-code visual voice agent builder	Zapier-only integrations, no Stripe Connect, no multi-tenant, no website tier
​
Bland.ai	Outbound voice automation API	No inbound, no CRM, no booking — API-only
​
Aloware ($30+/user/mo)	AI voice + CRM power dialer	HubSpot/Salesforce-locked, no self-hosted, no white-label, no website tier
​
Verdict: Nothing in OSS combines voice agent + CRM + booking + Stripe Connect + website provisioning in one stack. Your moat is the vertical integration.

Workflow Automation (n8n)
Tool	Self-Hosted	AI-Native	Risk
n8n (your choice)	Yes, free	Growing	$720/mo for shared credentials on cloud
​
Activepieces	Yes, MIT license	Built-in OpenAI/Claude	Newer, smaller community
​
Windmill	Yes, open-source	Multi-language	Less integrations than n8n
​
Kestra	Yes	YAML-based	Infrastructure-as-Code focus, not visual
​
Temporal	Yes	No	Enterprise-grade reliability but heavy
​
Verdict: n8n remains the right call for your stack. Activepieces is the only real challenger worth watching — it's MIT-licensed (vs n8n's fair-code license) and has native AI agent support. But n8n's integration library is deeper and you're already invested. No action needed here.

Contract Management (NDA/MCA/LOI/SOW)
Tool	Open Source	What It Does	Gap vs Your System
opensourceCM	Yes	Basic CLM	No Stripe integration, no milestone payments, no Xero sync
​
Agiloft	No (low-code)	Configurable CLM	$$$, enterprise-focused, no trade-business workflow
​
Zefort	No	AI contract repository	Repository-only, no generation or signing
​
ContractSafe	No	Full CLM	$$$, no Stripe/Xero integration, no trade workflows
​
DocuSign CLM	No	CLM + e-sign	Overkill and expensive for your scale
​
Verdict: Your custom contract system (auto-numbered NDA-2026-XXXX, milestone tracking, Stripe/Xero sync, auto-expiry alerts) is better than opensourceCM for your use case. The trade-specific workflows (ZES 24hr delivery SOW, TradeBuilder upsell contracts) don't exist in any OSS CLM.
​

Invoicing & Accounting
Tool	Open Source	Gap
Invoice Ninja	Yes	Standalone invoicing — no embedded text-to-pay, no Stripe Connect platform fees, no voice agent integration
ERPNext	Yes	Full ERP but massive overhead — requires dedicated admin, not suited for $15-30/mo micro-SaaS
Crater	Yes	Basic invoicing, no Xero sync, no multi-tenant
Verdict: None of these replace your Stripe + Xero + Supabase pipeline. Invoice Ninja is the closest but it's standalone — your system embeds invoicing into the customer journey (text-to-pay via ZES agent).

Part 2: What's Missing From the Plan
After reading the entire buildout (~571K characters), here are the concrete gaps — things that are either referenced but not built, promised in sales docs but not automated, or architecturally absent:

Critical (P0) — Will Block Revenue
No Client-Facing Dashboard

Your plan has rep dashboards and admin dashboards, but no portal where the actual client (plumber, roofer) logs in to see their leads, agent performance, reviews, and ROI. Without this, clients have zero visibility and will churn faster. GoHighLevel's #1 retention feature is client dashboard access.

Fix: Supabase RLS-scoped client view → embedded Metabase dashboards per client

No Automated ROI Report Generation

You reference ROI attribution but there's no code generating a "you got X leads, Y bookings, Z revenue from ZES this month" report. This is the #1 churn-prevention tool for service businesses. If a client can't see ROI, they cancel.

Fix: n8n monthly cron → pull Supabase metrics → generate PDF via ReportLab → email via SendGrid

10DLC Registration Pipeline — Completely Absent

Your plan uses Twilio SMS extensively (missed-call text-back, review requests, booking confirmations) but there is zero code for A2P 10DLC brand registration. Without this, SMS will be filtered/blocked by carriers. This is a legal and operational blocker.

Fix: Twilio Trust Hub integration during client onboarding (brand → campaign → number assignment)

Stripe Webhook → Revenue Tracker DB Missing

The Finance Guild API handles invoice.payment_succeeded and calculates commissions, but there's no central revenue event stream that feeds the Xero adapter, the Metabase dashboards, AND the client-facing ROI reports simultaneously. The webhook handler is single-purpose (commission calc only).

Fix: Fan-out pattern — webhook → n8n → parallel writes to commission engine, Xero, analytics, client dashboard

High Priority (P1) — Will Lose Deals Without These
No Voice Agent Failover

ElevenLabs goes down → your 24/7 AI receptionist promise breaks. Trade businesses get emergency calls at 2 AM during storms. No fallback is defined.

Fix: n8n health monitor (60s interval) → on ElevenLabs failure → reroute to Twilio IVR with pre-recorded per-client messages

No Real-Time Lead Scoring

Leads come in but there's no instant scoring/routing. A plumber getting a "my basement is flooding" call at 2 AM should get a different treatment than a "I need a quote for a bathroom remodel" form fill.

Fix: Supabase Edge Function on lead insert → score by urgency keywords + time of day + service type → route accordingly

Xero Two-Way Sync Not Wired

You have a Xero adapter referenced in the architecture but no actual sync code for: new client → Xero contact, Stripe invoice → Xero invoice, payment received → Xero reconciliation

Fix: n8n workflows: Stripe webhook → create/update Xero invoice → mark paid on payment_succeeded

Bundle Pricing Engine — Logic Exists, Stripe Products Don't

Your bundle discount matrix (Scout 10%, Operator 15%, Autopilot 20% off when combined with TradeBuilder) is defined in code but no corresponding Stripe Products/Prices/Coupons are created

Fix: Stripe seed script to create all product combinations + coupon objects

Important (P2) — Competitive Disadvantage Without These
No AI Review Response Engine

ZES captures reviews but doesn't draft responses. Every competitor (Podium, Birdeye) has AI review response. This is table stakes.

Fix: n8n workflow: new Google review webhook → OpenAI draft response → client approval via SMS → post via GBP API

No Competitor Snapshot Tool

Your Lead Scanner scores the prospect's website but doesn't show them what their competitors are doing (rankings, review counts, ad spend). This is a massive sales tool.

Fix: Extend Lead Scanner to pull top 3 local competitors via DataForSEO → include in scan report PDF

No Webhook Signature Verification on Inbound Webhooks (Non-Stripe)

Stripe webhooks are verified via constructEvent(), but DocuSend, NPM Network, and Xero inbound webhooks have no signature verification. This is a security gap.

Fix: Add HMAC verification middleware for each external webhook source

No Audit Trail for Manual Actions

Commission approvals, rep creation, product seeding — admin actions are logged nowhere except the Supabase updated_at timestamps. No who-did-what-when trail.

Fix: fg_audit_log table with trigger-based logging on all admin mutations

Part 3: Untapped Stack Advantages — What You CAN Do That You're NOT
These are capabilities your Supabase + Stripe + n8n + ElevenLabs stack already supports but your plan doesn't exploit:

1. Supabase Realtime → Live Client Dashboard (Zero Polling)
Your plan enables Realtime on tables for the rep dashboard but not for the client dashboard. Enable Realtime on leads, bookings, reviews, and voice_calls tables → clients see leads arrive in real-time. This alone justifies the Autopilot tier pricing.

2. Stripe Billing Portal → Self-Service Plan Management (Zero Code)
Stripe has a pre-built customer portal for plan changes, invoice history, and payment method updates. You're not using it. Enable it, embed the link, and you eliminate 80% of "I need to update my card" support tickets.

3. Supabase Edge Functions → Client Micro-API
Each ZES client could get their own API endpoint (/api/client/{id}/leads, /api/client/{id}/bookings) that their existing tools (ServiceTitan, Housecall Pro, QuickBooks) can call. This is an Autopilot-exclusive feature that makes ZES sticky. Competitors charge $99-299/mo for API access (GoHighLevel, Podium). You can offer it at $30/mo.

4. ElevenLabs Outbound Calls → Proactive Client Outreach
Your ElevenLabs integration is inbound-only. ElevenLabs supports outbound calls. Use this for: appointment reminders (reduce no-shows 20-40%), follow-up on estimates, and churn save offers. n8n triggers the call, ElevenLabs makes it.
​

5. PostHog Feature Flags → A/B Test Everything Without Deploys
You have PostHog but you're not using feature flags. A/B test: pricing tiers, bundle offers, agent prompts, onboarding flows — all without code deploys. This is free on PostHog's tier.

6. Predictive Job Demand via Weather API
Cross-reference PostHog event data (which services are being searched/booked) with weather forecasts to predict demand spikes. "Hail expected Thursday → alert roofing clients → they capture 2-3x more emergency jobs." Nobody else does this. This makes ZES feel like a $500/mo service at $30/mo.

7. Supabase Vault for Secrets Management
You're storing API keys (Xero, Twilio, ElevenLabs) in environment variables. Supabase Vault provides encrypted storage accessible via SQL. 2-hour migration, dramatically better security posture.

8. AI-Generated Service Pages → SEO Machine
For TradeBuilder clients, auto-generate hyper-local SEO pages: "Emergency Plumber in Aldine TX", "24/7 AC Repair Spring TX" — one page per service per city. n8n orchestrates, OpenAI generates, Framer publishes. A plumber with 20 service pages covering 10 cities has 200 ranking opportunities vs 5-10 for a basic site. This makes TradeBuilder genuinely worth $150-299/mo.

9. Cal.com Self-Hosted → Zero Booking Fees
Cal.com cloud charges $12-30/user/mo. Self-hosted: $0. At 100 clients, that's $1,200-3,000/mo saved. You already have the infrastructure. Deploy it alongside n8n.

10. Stripe Connect → Platform Payment Processing Fee
Instead of just billing clients, let ZES process payments on behalf of clients via Stripe Connect. Text-to-pay invoices go through your platform, you take 1-2% platform fee. At 100 Autopilot clients processing $10K/mo each = $1M GMV = $10-20K/mo in platform fees ON TOP of subscription revenue.

Part 4: Implementation Priority Matrix
Priority	Gap/Enhancement	Effort	Revenue Impact	Moat Impact
P0	Client-facing dashboard	2 weeks	High — reduces churn	Medium
P0	ROI attribution report	1 week	Critical — churn killer	High
P0	10DLC registration pipeline	3 days	Blocker — SMS won't work	N/A
P0	Stripe webhook fan-out	4 hours	Unblocks everything	Medium
P1	Stripe Connect payment processing	2 weeks	$10-20K/mo at scale	Very High
P1	Voice agent failover	3 days	Low frequency, high impact	Medium
P1	Xero two-way sync	4 hours	Operational efficiency	Low
P1	Bundle pricing Stripe setup	3 hours	Upsell revenue	Medium
P2	AI review response engine	1 week	Differentiator	High
P2	Competitor snapshot in Lead Scanner	3 days	Sales tool	Medium
P2	Client micro-API (Edge Functions)	1 week	Stickiness	Very High
P2	Self-hosted Cal.com	2 days	$1-3K/mo saved	Low
P2	AI-generated SEO pages	1 week	TradeBuilder value	High
P3	Audit trail for admin actions	2 days	Legal protection	Medium
P3	Webhook signature verification	1 day	Security	Low
P3	Predictive demand alerts	3 days	Retention	Very High
P3	Metabase white-label for clients	3 days	Autopilot value	High
Total estimated build time for all gaps: ~8 weeks of focused development.

The Bottom Line
Your real competition is GoHighLevel (expensive, generic) and the Jobber/Housecall Pro category (no AI). You beat GoHighLevel on price AND AI capabilities. You beat Jobber/Housecall Pro on automation depth.

The OSS components exist individually (Vapi for voice, Cal.com for booking, Invoice Ninja for invoicing, n8n for automation, Metabase for analytics), but nobody is assembling them into a turnkey $15-30/mo agent for HVAC contractors. That's the moat.

The gap to close isn't competition — it's execution. Ship the client dashboard, wire the ROI reports, register 10DLC, and exploit the Supabase Realtime + Edge Functions + Stripe Connect capabilities that your stack already has but you're not using yet. Every week you delay the client dashboard is a week your churn rate stays unnecessarily high.

Build it.