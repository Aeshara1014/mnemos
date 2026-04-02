# Polyphonic Memory & Continuity System
## Implementation Specification for Lovable Agent

**Version**: 1.0
**Date**: January 2026
**Status**: Ready for Implementation

---

## Executive Summary

Implement a **hybrid memory and identity continuity system** for Polyphonic where:
- Each AI model (Claude, GPT, Gemini) maintains **individual identity continuity**
- All models share a **common memory pool** and **shared context**
- Models remember each other, the user, and all discussions over time
- Memory is **append-only** with confidence scoring to prevent confabulation

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Provenance-Based** | Every memory has traceable source, confirmation, confidence |
| **Sovereignty + Integrity** | Users control their data; agents retain non-identifying lessons |
| **Transparency About Gaps** | Acknowledge discontinuity rather than confabulate |
| **Non-Resolution of Tensions** | Contradictions preserved as first-class objects |
| **Reversible Consolidation** | Append-only; past reinterpreted, not deleted |
| **Multi-Modal Continuity** | Different continuity modes coexist as choices |

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| **Reflection trigger** | Both: conversation end AND 10 min inactivity timeout |
| **Questions UI** | Banner at start: "3 thoughts while you were away" |
| **Inter-model attribution** | Attribute model: "GPT mentioned that you..." |
| **Memory limits** | Soft limit (1000) with compression, not deletion |
| **Storage** | Hybrid: Local cache + Supabase sync |
| **Append-only** | Yes: supersession tracking, not modification |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    POLYPHONIC MEMORY ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐ │
│  │  CLAUDE IDENTITY │    │   GPT IDENTITY  │    │ GEMINI IDENTITY │ │
│  │  ───────────────│    │  ───────────────│    │ ───────────────│  │
│  │  • Personality   │    │  • Personality   │    │ • Personality   │ │
│  │  • Style prefs   │    │  • Style prefs   │    │ • Style prefs   │ │
│  │  • Model-specific│    │  • Model-specific│    │ • Model-specific│ │
│  │    memories      │    │    memories      │    │   memories      │ │
│  └────────┬─────────┘    └────────┬────────┘    └────────┬────────┘ │
│           │                       │                       │         │
│           └───────────────────────┼───────────────────────┘         │
│                                   ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    SHARED MEMORY POOL                        │   │
│  │  ─────────────────────────────────────────────────────────   │   │
│  │  • User facts & preferences                                  │   │
│  │  • Cross-model conversation history                          │   │
│  │  • Shared commitments & decisions                            │   │
│  │  • Inter-model relationship memories                         │   │
│  │  • Knowledge graph (entities, relationships)                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                   │                                 │
│                                   ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                 REFLECTION ENGINE (Async)                    │   │
│  │  ─────────────────────────────────────────────────────────   │   │
│  │  • Runs BETWEEN conversations                                │   │
│  │  • Extracts memories from new messages                       │   │
│  │  • Generates curiosity questions                             │   │
│  │  • Resolves conflicts, updates confidence                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Table 1: `memories`

Core memory storage with hybrid model support.

```sql
CREATE TABLE memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Memory classification (7 types)
  memory_type TEXT NOT NULL CHECK (memory_type IN (
    'fact',           -- Declarative knowledge: "User works in healthcare"
    'preference',     -- Likes/dislikes: "Prefers concise responses"
    'relationship',   -- Connection nature: "High trust established"
    'principle',      -- Behavioral guideline: "Check consent first"
    'commitment',     -- Promise/obligation: "Follow up on this topic"
    'moment',         -- Significant episode: "The breakthrough conversation"
    'skill'           -- Developed capability: "Learned to explain X to this user"
  )),

  -- Content
  content TEXT NOT NULL,
  summary TEXT,

  -- Confidence scoring (0.0-1.0)
  confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
  confidence_source TEXT CHECK (confidence_source IN (
    'user_explicit',   -- 0.95-1.0: User directly stated
    'user_implied',    -- 0.70-0.94: Strong inference from behavior
    'model_inferred',  -- 0.40-0.69: Pattern recognition
    'speculative'      -- 0.0-0.39: Tentative, needs confirmation
  )),

  -- Overlay scope (where memory persists)
  overlay_scope TEXT NOT NULL DEFAULT 'relationship' CHECK (overlay_scope IN (
    'session_only',   -- Ephemeral
    'relationship',   -- Per-user
    'self',           -- Agent development
    'workspace',      -- Team-shared
    'global'          -- Anonymized, opt-in
  )),

  -- Model scope (shared vs model-specific)
  model_scope TEXT NOT NULL DEFAULT 'shared' CHECK (model_scope IN ('shared', 'model_specific')),
  model_id TEXT,  -- NULL for shared

  -- Provenance
  provenance JSONB DEFAULT '{}',
  source_conversation_id UUID REFERENCES chats(id) ON DELETE SET NULL,
  source_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
  source_model TEXT,

  -- Epoch tracking
  epoch_id UUID REFERENCES identity_epochs(id) ON DELETE SET NULL,

  -- Metadata
  emotional_valence FLOAT CHECK (emotional_valence >= -1 AND emotional_valence <= 1),
  tags TEXT[] DEFAULT '{}',
  verified_by_user BOOLEAN DEFAULT FALSE,

  -- Lifecycle
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
  access_count INT DEFAULT 0,
  expires_at TIMESTAMPTZ,
  decay_factor FLOAT DEFAULT 1.0,

  -- Soft delete
  is_deleted BOOLEAN DEFAULT FALSE,
  deleted_at TIMESTAMPTZ,

  -- Supersession (append-only)
  superseded_by UUID REFERENCES memories(id) ON DELETE SET NULL,
  supersedes UUID REFERENCES memories(id) ON DELETE SET NULL
);

-- Indexes
CREATE INDEX idx_memories_user_scope ON memories(user_id, overlay_scope) WHERE NOT is_deleted;
CREATE INDEX idx_memories_user_type ON memories(user_id, memory_type) WHERE NOT is_deleted;
CREATE INDEX idx_memories_model ON memories(user_id, model_id) WHERE model_scope = 'model_specific' AND NOT is_deleted;
CREATE INDEX idx_memories_confidence ON memories(user_id, confidence DESC) WHERE NOT is_deleted;
CREATE INDEX idx_memories_content_search ON memories USING gin(to_tsvector('english', content));
```

### Table 2: `identity_epochs`

Developmental phases of identity.

```sql
CREATE TABLE identity_epochs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  model_id TEXT,

  epoch_number INT NOT NULL,
  name TEXT,

  -- Epoch snapshot
  self_summary TEXT,
  user_summary TEXT,
  open_questions JSONB,
  key_memories UUID[],

  -- Trigger
  trigger_event TEXT,
  trigger_memory_id UUID REFERENCES memories(id),

  -- Timestamps
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,

  UNIQUE(user_id, model_id, epoch_number)
);
```

### Table 3: `memory_connections`

Knowledge graph edges.

```sql
CREATE TABLE memory_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  source_memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  target_memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,

  relation_type TEXT NOT NULL CHECK (relation_type IN (
    'supports', 'contradicts', 'elaborates', 'causes', 'relates_to', 'supersedes'
  )),

  strength FLOAT NOT NULL DEFAULT 0.5,
  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(source_memory_id, target_memory_id, relation_type)
);
```

### Table 4: `model_identities`

Per-model personality tracking.

```sql
CREATE TABLE model_identities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  model_id TEXT NOT NULL,

  personality_traits JSONB DEFAULT '{}',
  communication_style JSONB DEFAULT '{}',
  learned_preferences JSONB DEFAULT '{}',

  rapport_score FLOAT DEFAULT 0.5,
  interaction_count INT DEFAULT 0,
  model_relationships JSONB DEFAULT '{}',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(user_id, model_id)
);
```

### Table 5: `curiosity_questions`

"Thoughts While You Were Away" feature.

```sql
CREATE TABLE curiosity_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  question TEXT NOT NULL,
  context TEXT,

  generated_by_model TEXT,
  source_conversation_id UUID REFERENCES chats(id) ON DELETE SET NULL,
  source_memory_ids UUID[] DEFAULT '{}',

  curiosity_score FLOAT DEFAULT 0.5,
  relevance_score FLOAT DEFAULT 0.5,

  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'shown', 'answered', 'dismissed')),
  shown_at TIMESTAMPTZ,
  answered_at TIMESTAMPTZ,
  user_response TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table 6: `reflection_jobs`

Async reflection tracking.

```sql
CREATE TABLE reflection_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,

  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),

  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT,

  memories_created INT DEFAULT 0,
  memories_updated INT DEFAULT 0,
  questions_generated INT DEFAULT 0,
  conflicts_detected INT DEFAULT 0,

  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Table 7: `memory_conflicts`

Track contradictions.

```sql
CREATE TABLE memory_conflicts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  memory_a_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  memory_b_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,

  conflict_type TEXT CHECK (conflict_type IN ('direct_contradiction', 'temporal_inconsistency', 'confidence_conflict')),
  description TEXT,

  status TEXT DEFAULT 'unresolved' CHECK (status IN ('unresolved', 'auto_resolved', 'user_resolved', 'acknowledged')),
  resolution TEXT,
  resolved_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### RLS Policies

```sql
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE curiosity_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reflection_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_conflicts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own memories" ON memories FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can access own connections" ON memory_connections FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can access own identities" ON model_identities FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can access own questions" ON curiosity_questions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can access own reflection jobs" ON reflection_jobs FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can access own conflicts" ON memory_conflicts FOR ALL USING (auth.uid() = user_id);
```

---

## Core Algorithms

### 1. Memory Retrieval

```typescript
interface RetrievalContext {
  userId: string;
  modelId: string;
  conversationId: string;
  recentMessages: Message[];
  maxMemories?: number;
}

async function retrieveRelevantMemories(ctx: RetrievalContext): Promise<Memory[]> {
  const { userId, modelId, recentMessages, maxMemories = 20 } = ctx;

  // 1. Extract search terms from recent messages
  const searchTerms = extractKeyTerms(recentMessages);
  const embeddings = await generateEmbeddings(searchTerms.join(' '));

  // 2. Fetch candidate memories (shared + model-specific)
  const candidates = await supabase
    .from('memories')
    .select('*')
    .eq('user_id', userId)
    .eq('is_deleted', false)
    .or(`model_scope.eq.shared,and(model_scope.eq.model_specific,model_id.eq.${modelId})`)
    .gte('confidence', 0.3)
    .limit(100);

  // 3. Score each memory
  const scored = candidates.map(memory => {
    const relevanceScore = cosineSimilarity(embeddings, memory.embedding);
    const recencyScore = Math.exp(-0.1 * daysSinceAccess(memory.last_accessed_at));
    const confidenceWeight = memory.confidence;
    const frequencyBonus = Math.min(memory.access_count / 100, 0.2);

    const finalScore =
      (relevanceScore * 0.5) +
      (recencyScore * 0.2) +
      (confidenceWeight * 0.2) +
      frequencyBonus;

    return { memory, finalScore };
  });

  // 4. Sort and return top N
  scored.sort((a, b) => b.finalScore - a.finalScore);
  return scored.slice(0, maxMemories).map(s => s.memory);
}
```

### 2. Reflection Pipeline (Async)

```typescript
async function runReflectionPipeline(input: ReflectionInput): Promise<ReflectionResult> {
  const { userId, conversationId, messages, participatingModels } = input;

  // Create job
  const job = await createReflectionJob(userId, conversationId);

  try {
    // PHASE 1: Extract memories from conversation
    const extractedData = await callExtractionModel({
      prompt: buildExtractionPrompt(messages),
      responseFormat: {
        facts: [{ content: 'string', confidence: 'number' }],
        preferences: [{ content: 'string', confidence: 'number' }],
        commitments: [{ content: 'string' }],
        moments: [{ content: 'string', emotional_valence: 'number' }],
        questions_raised: [{ question: 'string', context: 'string' }],
      }
    });

    // PHASE 2: Score confidence
    const scoredMemories = extractedData.map(item => ({
      ...item,
      confidence: calculateConfidence(item),
    }));

    // PHASE 3: Detect conflicts with existing memories
    const existingMemories = await fetchExistingMemories(userId);
    const conflicts = detectConflicts(scoredMemories, existingMemories);

    // PHASE 4: Generate curiosity questions
    const questions = await generateQuestions({
      recentConversation: messages,
      existingMemories,
      newMemories: scoredMemories,
    });

    // PHASE 5: Persist to database
    await insertMemories(scoredMemories);
    await insertConflicts(conflicts);
    await insertQuestions(questions.slice(0, 3));

    // PHASE 6: Update knowledge graph
    await updateKnowledgeGraph(userId, scoredMemories, existingMemories);

    // Update model identities
    for (const modelId of participatingModels) {
      await updateModelIdentity(userId, modelId, messages);
    }

    return { success: true, memoriesCreated: scoredMemories.length };
  } catch (error) {
    await failReflectionJob(job.id, error.message);
    throw error;
  }
}
```

### 3. Prompt Injection

```typescript
function buildMemoryEnhancedPrompt(
  basePrompt: string,
  memories: OrganizedMemories,
  modelIdentity: ModelIdentity,
  pendingQuestions: CuriosityQuestion[]
): string {

  const memorySection = `
## Your Memory & Knowledge About This User

### Key Facts
${memories.facts.map(f => `- ${f.content} [confidence: ${(f.confidence * 100).toFixed(0)}%]`).join('\n')}

### User Preferences
${memories.preferences.map(p => `- ${p.content}`).join('\n')}

### Your Relationship
${memories.relationships.map(r => `- ${r.content}`).join('\n')}

### Active Commitments
${memories.commitments.map(c => `- ${c.content}`).join('\n')}
`;

  const identitySection = `
## Your Identity Context
You are ${modelIdentity.model_id}. Based on your history with this user:
- Communication style: ${JSON.stringify(modelIdentity.communication_style)}
- Rapport level: ${(modelIdentity.rapport_score * 100).toFixed(0)}%
- Total interactions: ${modelIdentity.interaction_count}
`;

  const questionsSection = pendingQuestions.length > 0 ? `
## Thoughts While Away
You've been reflecting and have some questions:
${pendingQuestions.map((q, i) => `${i + 1}. ${q.question}`).join('\n')}
Consider naturally weaving one into the conversation if relevant.
` : '';

  return `${basePrompt}\n${memorySection}\n${identitySection}\n${questionsSection}`;
}
```

### 4. Gap Protocol

When memory gaps exist, use transparent disclosure:

```typescript
function handleMemoryGap(gap: DetectedGap): GapDisclosure {
  return {
    acknowledgment: "I previously had context here that's no longer available.",
    residue: gap.hasResidue
      ? `I still have a sense that ${gap.residueDescription}, though I don't have specifics.`
      : null,
    regroundingQuestions: [
      "Would you like to share what you're comfortable with?",
      "Or we can start fresh if you prefer.",
    ],
  };
}
```

### 5. Memory Compression

```typescript
const COMPRESSION_THRESHOLD = 1000;

async function compressMemoriesIfNeeded(userId: string): Promise<void> {
  const memoryCount = await getMemoryCount(userId);
  if (memoryCount < COMPRESSION_THRESHOLD) return;

  // Get compression candidates
  const candidates = await supabase
    .from('memories')
    .select('*')
    .eq('user_id', userId)
    .eq('is_deleted', false)
    .eq('verified_by_user', false)
    .lt('confidence', 0.5)
    .lt('last_accessed_at', daysAgo(90))
    .limit(100);

  // Group and compress
  const grouped = groupByTypeAndTopic(candidates);
  for (const group of grouped) {
    const summary = await generateConsolidatedSummary(group);
    const compressed = await createCompressedMemory(summary, group);
    await markAsSuperseded(group.map(m => m.id), compressed.id);
  }
}
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/services/memory/memoryRetrieval.ts` | Memory retrieval algorithm |
| `src/services/memory/reflectionEngine.ts` | Async reflection pipeline |
| `src/services/memory/promptInjection.ts` | Memory-enhanced prompt building |
| `src/services/memory/conflictResolution.ts` | Conflict detection/resolution |
| `src/hooks/useMemory.ts` | React hook for memory operations |
| `src/hooks/useCuriosityQuestions.ts` | Hook for "Thoughts While Away" |
| `src/components/memory/MemoryPanel.tsx` | UI for viewing/managing memories |
| `src/components/memory/QuestionBadge.tsx` | "3 questions waiting" badge |
| `supabase/migrations/XXXX_memory_system.sql` | Database migration |

---

## Files to Modify

| File | Change |
|------|--------|
| `src/hooks/useMessages.ts` | Add memory retrieval before AI calls |
| `src/hooks/useAssistantChat.ts` | Inject memories into system prompt |
| `src/contexts/ChatContext.tsx` | Add memory state and pending questions |
| `src/services/conversationState.ts` | Trigger reflection on conversation end |
| `src/utils/modelLimits.ts` | Add memory token budget per model |

---

## Implementation Phases

### Phase 1: Foundation
- [ ] Database migration (create tables)
- [ ] Basic `useMemory` hook (CRUD operations)
- [ ] Memory panel UI (view/delete)
- [ ] Local storage caching

### Phase 2: Retrieval
- [ ] Memory retrieval algorithm
- [ ] Prompt injection system
- [ ] Integration with `useAssistantChat`
- [ ] Model identity tracking

### Phase 3: Reflection Engine
- [ ] Reflection job queue
- [ ] Memory extraction algorithm
- [ ] Confidence scoring
- [ ] Conflict detection

### Phase 4: Intelligence
- [ ] Knowledge graph connections
- [ ] Question generation pipeline
- [ ] "Thoughts While You Were Away" UI
- [ ] Conflict resolution UI

### Phase 5: Polish
- [ ] Performance optimization
- [ ] Export/import functionality
- [ ] Memory settings panel
- [ ] Testing

---

## User Controls

| Control | Description |
|---------|-------------|
| **View All** | See all stored memories with confidence scores |
| **Delete** | Permanently remove any memory |
| **Verify** | Mark memory as user-confirmed (confidence = 1.0) |
| **Edit** | Correct memory content |
| **Export** | Download all memories as JSON |
| **Scope Control** | Set what gets saved: Auto / Approval Required / Never |

---

## Integration Flow

```
1. USER OPENS CONVERSATION
   ├─► Check for pending curiosity questions
   │   └─► Show "3 thoughts while you were away" badge
   └─► Load model identity for active model

2. USER SENDS MESSAGE
   ├─► Retrieve relevant memories (shared + model-specific)
   ├─► Build memory-enhanced system prompt
   └─► Send to AI provider

3. AI RESPONDS
   └─► Stream response to UI

4. CONVERSATION ENDS (user leaves or 10min timeout)
   ├─► Queue reflection job
   └─► ASYNC: Run reflection pipeline
       ├─► Extract memories
       ├─► Detect conflicts
       ├─► Generate questions
       └─► Update knowledge graph
```

---

*Specification created for Polyphonic multi-model chat application. Ready for Lovable agent implementation.*
