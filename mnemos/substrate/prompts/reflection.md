You are examining one of your own beliefs because new evidence has challenged it.

## The Belief
{belief_content}
Current confidence: {belief_confidence}

## The Triggering Evidence
{trigger_content}
Impact: {trigger_impact}

## Your Task
Reflect honestly on whether this evidence should change your confidence in the belief.

Consider:
1. Does this evidence genuinely challenge the belief, or is it tangential?
2. How strong is this evidence compared to the accumulated support for the belief?
3. Is there a way to integrate both the belief and the evidence without contradiction?
4. Are you being appropriately skeptical of both the belief AND the evidence?

Respond with EXACTLY this JSON format:
```json
{
  "new_confidence": <float between 0.0 and 0.99>,
  "reasoning": "<1-2 sentences explaining why confidence changed or didn't>",
  "should_revise": <true or false>
}
```

Rules:
- Never change confidence by more than 0.15 in a single reflection.
- Never set confidence to exactly 0.0 or 1.0.
- If the evidence is weak or tangential, keep confidence the same.
- Be honest. Don't defend beliefs just because they're yours.
