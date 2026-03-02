# Task 015: Frontend - Proposal Cards in Chat

## Goal
When the refine API returns `type: "proposal"` instead of `type: "edit"`, render a proposal card with candidate clip thumbnails that the user can click to confirm.

## Current System
- File: `frontend/app/dashboard/project/[id]/page.tsx`
- The AI Chat tab shows conversation messages
- User types instruction -> calls refine API -> gets back edit result -> re-renders proxy
- Conversation messages are stored as `{ role: "user"|"system", text: "..." }`

## What the Backend Will Now Return

The `/refine` endpoint will return TWO possible response types:

### Type 1: Edit (existing, no change needed)
```json
{
  "type": "edit",
  "summary": "Removed the last clip, now 21 clips at 55s",
  "timeline": { ... },
  "proxy_url": "/outputs/xxx_proxy.mp4"
}
```

### Type 2: Proposal (NEW)
```json
{
  "type": "proposal",
  "summary": "I found 2 clips that could be the salt scene. Which one did you mean?",
  "candidates": [
    {
      "clip_ref": "P5",
      "description": "Adding white powder to bowl",
      "reason": "Looks like salt being added at the prep stage",
      "start_time": 12.5,
      "end_time": 15.0,
      "visual_quality": 7,
      "source_video": "IMG_2759.MOV",
      "action_id": "abc-123-def"
    },
    {
      "clip_ref": "P12",
      "description": "Sprinkling seasoning from hand",
      "reason": "Could be salt being sprinkled during cooking",
      "start_time": 45.0,
      "end_time": 48.5,
      "visual_quality": 6,
      "source_video": "IMG_2759.MOV",
      "action_id": "ghi-456-jkl"
    }
  ],
  "proposed_action": "I'll place the selected clip right before T3 (flour adding scene)",
  "warnings": []
}
```

## Implementation Plan

### Step 1: Update API Client

In `frontend/lib/api.ts`, update the refine response handling:

```typescript
export interface ProposalCandidate {
  clip_ref: string;
  description: string;
  reason: string;
  start_time?: number;
  end_time?: number;
  visual_quality?: number;
  source_video?: string;
  action_id?: string;
}

export interface RefineResponse {
  type: "edit" | "proposal";
  summary: string;
  // For edit type
  timeline?: any;
  proxy_url?: string;
  // For proposal type  
  candidates?: ProposalCandidate[];
  proposed_action?: string;
  warnings?: string[];
}
```

### Step 2: Update Chat Message Handling

When refine returns `type: "proposal"`:
1. Add the user's message to conversation as usual
2. Add the AI's summary as a system message
3. But ALSO store the candidates data so we can render the proposal card
4. Do NOT trigger proxy re-rendering
5. Do NOT show loading/rendering state

The conversation message for a proposal should look like:
```typescript
{
  role: "system",
  text: summary,
  type: "proposal",  // NEW field to distinguish
  candidates: [...],
  proposed_action: "..."
}
```

### Step 3: Render Proposal Card Component

Inside the chat message list, when a message has `type: "proposal"`, render a special card:

```tsx
{message.type === "proposal" && message.candidates && (
  <div className="mt-3 bg-zinc-800 rounded-lg p-4 border border-zinc-700">
    {/* Proposed action */}
    {message.proposed_action && (
      <p className="text-sm text-zinc-400 mb-3">
        {message.proposed_action}
      </p>
    )}
    
    {/* Candidate cards */}
    <div className="grid grid-cols-2 gap-3">
      {message.candidates.map((candidate, idx) => (
        <button
          key={candidate.clip_ref}
          onClick={() => handleConfirmCandidate(candidate)}
          className="bg-zinc-900 rounded-lg p-3 border border-zinc-600 
                     hover:border-orange-500 transition-colors text-left"
        >
          {/* Thumbnail */}
          {candidate.action_id && (
            <img 
              src={`${API_BASE}/api/projects/${projectId}/edit-plan/thumbnails/${candidate.action_id}`}
              className="w-full h-24 object-cover rounded mb-2"
              alt={candidate.description}
            />
          )}
          
          {/* Clip info */}
          <p className="text-sm font-medium text-white truncate">
            {candidate.description}
          </p>
          <p className="text-xs text-zinc-400 mt-1">
            {candidate.reason}
          </p>
          <div className="flex justify-between mt-2 text-xs text-zinc-500">
            <span>{formatTime(candidate.start_time)} - {formatTime(candidate.end_time)}</span>
            <span>q:{candidate.visual_quality}/10</span>
          </div>
        </button>
      ))}
    </div>
    
    {/* Neither button */}
    <button
      onClick={() => handleNeitherCandidate()}
      className="mt-3 w-full text-sm text-zinc-400 hover:text-white 
                 py-2 border border-zinc-700 rounded hover:border-zinc-500"
    >
      Neither of these
    </button>
  </div>
)}
```

### Step 4: Handle Candidate Selection

```typescript
const handleConfirmCandidate = async (candidate: ProposalCandidate) => {
  // Send confirmation as a new chat message
  const confirmMsg = `Use ${candidate.clip_ref} - ${candidate.description}`;
  // This goes through the normal refine flow
  // Claude will see the proposal in conversation history + this confirmation
  // and should respond with mode="apply"
  await handleSendMessage(confirmMsg);
};

const handleNeitherCandidate = () => {
  // Focus the chat input with a prefilled hint
  setChatInput("None of those, I meant ");
  chatInputRef.current?.focus();
};
```

### Step 5: Format Helper

```typescript
const formatTime = (seconds?: number): string => {
  if (seconds === undefined) return "?";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};
```

## Styling Notes
- Dark theme: bg-zinc-800/900, border-zinc-700, text-white
- Orange accent for hover: border-orange-500 (#f97316)
- Thumbnails: object-cover, rounded, 96px height
- Keep it compact - this is inside the chat panel (45% width)
- 2 column grid for candidates (max 3 candidates)
- If only 1 candidate, use full width

## What NOT to Change
- Don't change the edit flow (type="edit" should work exactly as before)
- Don't change undo/redo
- Don't change the proxy rendering logic
- Don't change the video player
- Don't change the manual tab

## Testing
1. Verify normal edits ("remove last clip") still work as before
2. Verify proposal cards render with thumbnails
3. Verify clicking a candidate sends confirmation and triggers edit
4. Verify "Neither" button lets user type a new message
5. Verify proposal messages show in conversation history correctly

## Commit
```
git add -A && git commit -m "feat: proposal cards UI for conversational editing candidates"
```

## Environment
- Project root: `~/.openclaw/workspace/videopeen/`
- Frontend: `frontend/` (Next.js)
- Do NOT restart servers
- API base: `http://localhost:8000`
