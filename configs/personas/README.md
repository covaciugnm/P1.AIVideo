# configs/personas/

On-screen persona specs. Referenced from briefs by stable id.

## Schema (planned)

```yaml
id: caucasian_male_30s_neutral
display_name: "Neutral male, 30s"
demographic:
  ethnicity: white_caucasian        # fixed by project scope
  apparent_age_range: [30, 39]
  apparent_gender: male
appearance:
  attire: business_casual
  hair: short_brown
  framing: head_and_shoulders
notes: >
  Synthetic only. No reference to real individuals. Negative prompt
  enforces this at generation time.
```

Persona files are validated against a Pydantic schema on backend startup.
