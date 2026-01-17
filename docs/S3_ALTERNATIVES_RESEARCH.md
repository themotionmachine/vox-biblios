# S3 Alternatives for Audio Hosting - Research Document

This document evaluates alternatives to Amazon S3 for hosting podcast audio files in Vox Biblios.

## Current Architecture

Vox Biblios currently uses:
- **AWS Polly** for text-to-speech conversion
- **Amazon S3** for storing audio files and RSS feeds

### Critical Integration Consideration

The current implementation uses Polly's `start_speech_synthesis_task()` API, which **requires S3** as the output destination. This API supports up to 100,000 billable characters (used for long-form content like book chapters).

The alternative `SynthesizeSpeech` API returns a byte stream that can be stored anywhere, but is limited to **3,000 billable characters** per request.

**Implication**: Any migration to alternative storage requires either:
1. Keep S3 for Polly output → copy/sync to alternative storage
2. Switch to `SynthesizeSpeech` API with smaller chunks (more API calls)
3. Use a different TTS provider entirely

---

## S3-Compatible Storage Alternatives

### 1. Cloudflare R2 ⭐ Recommended

| Aspect | Details |
|--------|---------|
| **Pricing** | $0.015/GB/month storage |
| **Egress** | **$0 (free)** |
| **Operations** | $4.50/million Class A, $0.36/million Class B |
| **Free Tier** | 10 GB storage, 1M operations/month |
| **S3 Compatible** | Yes (drop-in replacement) |
| **CDN** | Cloudflare's global network included |

**Pros:**
- Zero egress fees - huge savings for podcast distribution
- S3-compatible API works with boto3
- Cloudflare's CDN included automatically
- Generous free tier covers small podcasts

**Cons:**
- Requires Cloudflare account
- Polly still needs S3 for async synthesis (would need sync workflow)

**Cost Example**: 10 GB storage + 100 GB downloads/month = $0.15/month (vs ~$9+ on S3)

---

### 2. Backblaze B2

| Aspect | Details |
|--------|---------|
| **Pricing** | $0.005/GB/month storage |
| **Egress** | Free up to 3x storage; $0.01/GB after |
| **Free Tier** | 10 GB storage |
| **S3 Compatible** | Yes |
| **CDN Partners** | Free egress via Cloudflare, Fastly, bunny.net |

**Pros:**
- Cheapest storage pricing
- S3-compatible API
- Free unlimited egress through CDN partners (Cloudflare)
- Excellent for archival/backup use cases

**Cons:**
- Egress can get expensive without CDN partner
- No built-in CDN (but works great with Cloudflare CDN)

**Best Setup**: Backblaze B2 + Cloudflare CDN = free egress + cheap storage

**Cost Example**: 10 GB storage = $0.05/month (egress free via Cloudflare)

---

### 3. Wasabi

| Aspect | Details |
|--------|---------|
| **Pricing** | $0.0069/GB/month ($6.99/TB) |
| **Egress** | Free (up to 1:1 storage ratio) |
| **Minimum** | 1 TB monthly charge (~$6.99/month) |
| **S3 Compatible** | 100% AWS S3/IAM API compatible |
| **Regions** | 14+ global regions |

**Pros:**
- 80% cheaper than AWS S3
- No egress fees (with reasonable usage)
- Full S3 API compatibility
- No API request fees

**Cons:**
- **1 TB minimum monthly charge** - overkill for small podcasts
- Egress must not exceed storage volume
- 90-day minimum storage duration

**Best For**: Larger podcast libraries (100+ GB)

---

### 4. DigitalOcean Spaces

| Aspect | Details |
|--------|---------|
| **Pricing** | $5/month base (includes 250 GB storage) |
| **Egress** | 1 TB included; $0.01/GB after |
| **S3 Compatible** | Yes |
| **CDN** | Built-in, included at no cost |

**Pros:**
- Simple, predictable pricing
- Built-in CDN at no extra cost
- S3-compatible API
- Great if already using DigitalOcean

**Cons:**
- $5/month minimum even for tiny usage
- Less flexible than pure pay-as-you-go

**Best For**: Medium-sized podcasts; users already on DigitalOcean

---

### 5. Google Cloud Storage

| Aspect | Details |
|--------|---------|
| **Pricing** | $0.020/GB/month (Standard) |
| **Egress** | $0.12/GB (North America) |
| **Free Tier** | 5 GB/month |
| **S3 Compatible** | Via interoperability mode |

**Pros:**
- Enterprise-grade reliability
- 24+ global regions
- Excellent for multi-cloud setups

**Cons:**
- Expensive egress fees
- More complex than S3
- Not directly S3-compatible (needs adapter)

---

### 6. MinIO (Self-Hosted)

| Aspect | Details |
|--------|---------|
| **Pricing** | Free (open source) + infrastructure costs |
| **Egress** | Only bandwidth costs from your host |
| **S3 Compatible** | 100% S3 API compatible |

**Pros:**
- No vendor lock-in
- Complete control over data
- No licensing fees
- Can run on any infrastructure

**Cons:**
- Requires self-management
- Need reliable hosting with good bandwidth
- No built-in CDN
- Operational overhead

---

## Comparison Summary

| Provider | Storage | Egress | Min Cost | CDN | Best For |
|----------|---------|--------|----------|-----|----------|
| **Cloudflare R2** | $0.015/GB | **Free** | ~$0 | ✅ Included | High-download podcasts |
| **Backblaze B2** | $0.005/GB | Free via CDN | ~$0 | Via partner | Budget-conscious |
| **Wasabi** | $0.007/GB | Free* | $6.99/mo | ❌ | Large libraries (>100GB) |
| **DO Spaces** | Incl. 250GB | 1TB incl. | $5/mo | ✅ Included | DO users, simplicity |
| **AWS S3** | $0.023/GB | $0.09/GB | ~$0 | Extra cost | Polly integration |
| **MinIO** | Free | Infra cost | Varies | ❌ | Self-hosters |

---

## Recommended Approaches

### Option A: Hybrid (Lowest Friction) ⭐

Keep S3 for Polly output, sync to Cloudflare R2 for distribution.

```
Polly → S3 (temporary) → sync → Cloudflare R2 (public distribution)
                              → Update RSS with R2 URLs
```

**Pros**: No code changes to Polly integration
**Cons**: Still some S3 costs, added sync complexity

### Option B: Backblaze B2 + Cloudflare CDN

Use Backblaze B2 for storage with Cloudflare as CDN (free egress partnership).

```
Polly → S3 (temporary) → upload → Backblaze B2
                              → Serve via Cloudflare CDN (free egress)
```

**Cost**: ~$0.05/month for 10GB (storage only)

### Option C: Full Cloudflare R2 Migration

Modify Polly integration to use `SynthesizeSpeech` API (sync, returns bytes) and upload directly to R2.

```
Text → Polly SynthesizeSpeech → bytes → upload → Cloudflare R2
```

**Pros**: Eliminates S3 entirely, zero egress costs
**Cons**: Requires code changes, smaller chunk sizes (3K chars)

### Option D: DigitalOcean Spaces

Simple switch if you want predictable pricing and included CDN.

**Cost**: $5/month flat (up to 250GB + 1TB transfer)

---

## Implementation Notes

### For Cloudflare R2 or Backblaze B2

Both are S3-compatible. Modify `vox_biblios/aws/s3.py`:

```python
# Example: Using boto3 with R2
s3_client = boto3.client(
    's3',
    endpoint_url='https://<account_id>.r2.cloudflarestorage.com',
    aws_access_key_id='<r2_access_key>',
    aws_secret_access_key='<r2_secret_key>',
)
```

### RSS Feed URL Update

The RSS feed would need URLs updated to point to the new storage:
- Current: `https://s3.{region}.amazonaws.com/{bucket}/audio/...`
- R2: `https://{bucket}.{account}.r2.cloudflarestorage.com/audio/...`
- Or custom domain with Cloudflare

---

## Conclusion

**For most Vox Biblios users, Cloudflare R2 is the best alternative** due to:
- Zero egress fees (critical for podcast downloads)
- Built-in global CDN
- S3-compatible API (minimal code changes)
- Generous free tier

For users with larger storage needs (>100GB), **Backblaze B2 + Cloudflare CDN** offers the cheapest storage with free egress.

The main architectural consideration is that **Polly's async API requires S3**, so a hybrid approach (Polly → S3 → sync to alternative) may be most practical unless switching to the synchronous API with smaller chunks.

---

## Sources

- [Cloudflare R2 Pricing](https://developers.cloudflare.com/r2/pricing/)
- [Cloudflare R2 Product Page](https://www.cloudflare.com/developer-platform/products/r2/)
- [Backblaze B2 S3 Compatible API](https://www.backblaze.com/blog/backblaze-b2-s3-compatible-api/)
- [Backblaze Cloud Storage Pricing](https://www.backblaze.com/cloud-storage/pricing)
- [Wasabi Pricing](https://wasabi.com/pricing)
- [Wasabi Pricing FAQ](https://wasabi.com/pricing/faq)
- [DigitalOcean Spaces Pricing](https://docs.digitalocean.com/products/spaces/details/pricing/)
- [DigitalOcean Spaces Product Page](https://www.digitalocean.com/products/spaces)
- [AWS Polly StartSpeechSynthesisTask](https://docs.aws.amazon.com/polly/latest/dg/API_StartSpeechSynthesisTask.html)
- [AWS Polly SynthesizeSpeech](https://docs.aws.amazon.com/polly/latest/dg/API_SynthesizeSpeech.html)
