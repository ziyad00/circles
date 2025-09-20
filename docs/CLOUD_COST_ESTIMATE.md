### Cloud Cost Estimate for Circles (AWS ECS + FastAPI + Postgres)

This document provides a practical, stage‑by‑stage estimate of monthly costs for Circles based on our current stack:

- Compute: FastAPI on ECS/Fargate behind an ALB (WebSockets hosted by us)
- Database: Postgres on Amazon RDS
- Media: S3 storage + CloudFront CDN
- Realtime: Native WebSockets on ALB/ECS (no third‑party)
- Maps: OSM/Overpass with optional Foursquare fallback
- Push: APNs/FCM (free), optional SNS fan‑out later

All prices are ballpark USD in us‑east‑1 and rounded.

---

## Assumptions

- Usage tiers
  - Early: ≤5K MAU (~1K DAU), ~50K API req/day, ~5K media views/day
  - Growth: 5K–25K MAU (~5K DAU), ~250K API req/day, ~50K media views/day
  - Scale: 25K–100K MAU (~20K DAU), ~1M API req/day, ~250K media views/day
- Single region, moderate logging, CloudFront in front of S3 for media
- FSQ trending/data is feature‑flagged and may add cost when enabled

---

## One‑time / Annual Setup

| Item                  |         Cost | Why                           |
| --------------------- | -----------: | ----------------------------- |
| Apple Developer       |     $99/year | Required for iOS/App Store    |
| Google Play Developer | $25 one‑time | Required for Play Store       |
| Domain                |  $10–20/year | Registrar (Route53 or other)  |
| SSL/TLS               |           $0 | AWS ACM certificates are free |

---

## Monthly Operating Costs (by stage)

| Service                            | Early (≤5K MAU) | Growth (5K–25K) | Scale (25K–100K) | Why / Notes                                                            |
| ---------------------------------- | --------------: | --------------: | ---------------: | ---------------------------------------------------------------------- |
| Compute: ECS/Fargate + ALB         |         $60–180 |        $150–450 |       $400–1,200 | 2–6 tasks (0.25–1 vCPU, 0.5–2GB) + ALB hours + modest LCUs for WS/HTTP |
| Database: RDS Postgres             |          $25–80 |         $80–250 |         $250–700 | t4g.micro→t4g.medium; 20–200GB storage; Multi‑AZ at growth+            |
| Media storage (S3)                 |          $10–40 |         $25–120 |          $80–300 | $0.023/GB‑mo; metadata + originals; requests are minor                 |
| Media delivery (CloudFront)        |         $30–120 |        $120–450 |       $400–1,600 | Egress dominates; ~$0.085/GB first 10TB + request fees                 |
| Realtime (WebSockets on ALB/ECS)   |          $10–40 |         $40–140 |         $120–400 | ALB LCUs + extra task capacity for concurrent WS                       |
| Maps/Location (OSM + FSQ fallback) |           $0–25 |         $25–150 |         $100–400 | OSM free; FSQ paid only when enabled/at scale                          |
| Push notifications (APNs/FCM)      |           $0–10 |           $0–25 |            $0–50 | Mostly free; SNS fan‑out optional later                                |
| Logs & monitoring (CloudWatch)     |           $5–30 |          $20–80 |          $80–250 | Ingestion + retention; sample app logs to save cost                    |
| DNS (Route53)                      |            $1–5 |           $1–10 |            $2–20 | Hosted zone + queries                                                  |

### Estimated Monthly Total

- Early: **$141–550**/month
- Growth: **$561–1,675**/month
- Scale: **$1,352–4,920**/month

> Note: These totals are higher than screenshots that lump “storage” and “delivery” because CDN egress (not S3 storage) is the dominant cost at scale. We also model Postgres on RDS with Multi‑AZ at Growth/Scale.

---

## Why these numbers (quick formulas)

- **Fargate**: cost ≈ vCPU‑hrs × rate + GB‑hrs × rate; 2 tiny tasks 24/7 + ALB can be ~$50–$120/mo; add tasks for autoscaling/WS.
- **ALB LCUs**: increase with new connections/active WS/processed bytes; budget modest LCUs early, rising with DAU.
- **RDS Postgres**: t4g.micro ≈ $12–$20/mo compute + storage; Multi‑AZ roughly 2× compute at Growth+.
- **S3**: $0.023/GB‑mo; storage itself is inexpensive.
- **CloudFront egress**: ~$0.085/GB (first 10TB in NA/EU). 1TB egress ≈ $85/mo; 10TB ≈ $850/mo.
- **Maps**: OSM free; paid FSQ calls are flag‑controlled.
- **Push**: APNs/FCM free; SNS adds ~$0.50–$1.00 per million notifications + data transfer.

---

## Key Cost Drivers

- Media delivery egress (CDN) scales with views and video length.
- Concurrency for realtime (WebSockets) -> more ECS tasks + ALB LCUs.
- Database HA (Multi‑AZ) and potential read replicas at Growth/Scale.
- External APIs (FSQ, geocoding) when enabled.

---

## Cost Reduction Tips

- Aggressive CloudFront caching (long TTLs for immutable media), smaller bitrates.
- Serve thumbnails/preview variants; lazy/original on demand.
- Autoscale ECS by CPU and connection count; keep background workers minimal.
- Short CloudWatch retention; sample logs in app.
- Keep FSQ usage behind a feature flag (current default).

---

## TL;DR vs generic templates

- We use **RDS Postgres** (not MongoDB Atlas).
- Split **S3 storage** from **CDN delivery**—egress dominates at scale.
- Realtime is **self‑hosted WebSockets** on ALB/ECS (no third‑party SaaS fees).
- Estimates include logging and DNS often missed in simple tables.
