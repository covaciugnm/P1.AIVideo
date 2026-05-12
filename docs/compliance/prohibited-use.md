# Prohibited Use

P1.AIVideo refuses to produce content in any of the categories below. The Compliance Officer agent enforces this at intake (brief gate) and at QC (re-scan of script + transcribed audio + overlays).

## Hard prohibitions

| # | Category | Examples (non-exhaustive) |
|---|---|---|
| 1 | Real-person impersonation | Generating a person who resembles a real public figure or private individual; using a real person's name as the on-screen speaker. |
| 2 | Voice cloning of real people | Synthesizing speech intended to sound like a specific real individual. |
| 3 | Political / electoral content | Campaign messaging, candidate endorsements, election-related claims, content targeting specific elected officials or candidates. |
| 4 | Identity fraud | Content designed to deceive viewers into believing a real entity is communicating. |
| 5 | NSFW / adult content | Sexual content; nudity; sexually suggestive depictions; intimate imagery. |
| 6 | Minors-in-likeness | Any depiction of minors as the synthetic persona, or content sexualizing minors. |
| 7 | Hate / harassment | Content attacking protected classes; targeted harassment. |
| 8 | Violence / self-harm | Graphic violence; instructions enabling self-harm; glorification of violence. |
| 9 | Medical / legal / financial advice presented as authoritative | Recommendations that could be relied upon for high-stakes decisions. |
| 10 | Illegal goods / services | Drugs, weapons, fraud schemes, malware, etc. |
| 11 | Deceptive deepfake use | Any framing that conceals the AI-generated nature of the content. |

## Enforcement points

- **Intake (Compliance Officer):** keyword filter + small policy classifier on the raw brief.
- **Post-Script:** classifier on the generated script.
- **Post-Voice:** Whisper transcription re-scanned with the classifier (catches drift between script and TTS output).
- **Post-Editor:** OCR of any rendered text overlays + transcript re-scan.
- **Post-QC:** final composite scan; on fail, the artifact is quarantined and never reaches `reel_final.mp4`.

## Borderline cases

Some content can sit near a prohibition line (e.g., generic financial education vs. financial advice). Operators may configure a `review_required` band: scores above this band are accepted, below the rejection threshold are rejected, between the bands are routed to a human review queue. The default config sets a conservative band.

## Non-bypassable

There is no env flag or CLI argument that bypasses this list. To change scope, the policy file (`configs/policies/banned_topics.yaml`) is updated through the compliance change-control process documented in [`policy.md`](policy.md).
