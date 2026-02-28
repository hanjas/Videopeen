#!/bin/bash
# Verification script for Task 005: Text Overlays (Backend)

echo "🔍 Verifying Task 005 Implementation..."
echo ""

errors=0

# 1. Check new file exists
echo "1️⃣ Checking new file..."
if [ -f "backend/app/services/text_overlay.py" ]; then
    echo "   ✅ text_overlay.py exists"
else
    echo "   ❌ text_overlay.py NOT FOUND"
    ((errors++))
fi

# 2. Check modified files
echo ""
echo "2️⃣ Checking modified files..."
if grep -q "from app.services.text_overlay import" backend/app/routers/edit_plan.py; then
    echo "   ✅ edit_plan.py imports text_overlay"
else
    echo "   ❌ edit_plan.py missing import"
    ((errors++))
fi

if grep -q "from app.services.text_overlay import" backend/app/services/render.py; then
    echo "   ✅ render.py imports text_overlay"
else
    echo "   ❌ render.py missing import"
    ((errors++))
fi

# 3. Check API endpoints
echo ""
echo "3️⃣ Checking API endpoints..."
if grep -q '@router.get("/overlays")' backend/app/routers/edit_plan.py; then
    echo "   ✅ GET /overlays endpoint exists"
else
    echo "   ❌ GET /overlays endpoint missing"
    ((errors++))
fi

if grep -q '@router.post("/overlays")' backend/app/routers/edit_plan.py; then
    echo "   ✅ POST /overlays endpoint exists"
else
    echo "   ❌ POST /overlays endpoint missing"
    ((errors++))
fi

if grep -q '@router.post("/overlays/auto-generate")' backend/app/routers/edit_plan.py; then
    echo "   ✅ POST /overlays/auto-generate endpoint exists"
else
    echo "   ❌ POST /overlays/auto-generate endpoint missing"
    ((errors++))
fi

# 4. Check Pydantic models
echo ""
echo "4️⃣ Checking Pydantic models..."
if grep -q "class TextOverlay" backend/app/routers/edit_plan.py; then
    echo "   ✅ TextOverlay model exists"
else
    echo "   ❌ TextOverlay model missing"
    ((errors++))
fi

if grep -q "class UpdateOverlaysRequest" backend/app/routers/edit_plan.py; then
    echo "   ✅ UpdateOverlaysRequest model exists"
else
    echo "   ❌ UpdateOverlaysRequest model missing"
    ((errors++))
fi

# 5. Check render integration
echo ""
echo "5️⃣ Checking render integration..."
if grep -q "apply_text_overlays" backend/app/services/render.py; then
    echo "   ✅ render.py calls apply_text_overlays()"
else
    echo "   ❌ render.py missing overlay integration"
    ((errors++))
fi

if grep -q "text_overlays = edit_plan.get" backend/app/services/render.py; then
    echo "   ✅ render.py reads text_overlays from edit_plan"
else
    echo "   ❌ render.py doesn't read text_overlays"
    ((errors++))
fi

# 6. Check key functions in text_overlay.py
echo ""
echo "6️⃣ Checking text_overlay.py functions..."
if grep -q "def apply_text_overlays" backend/app/services/text_overlay.py; then
    echo "   ✅ apply_text_overlays() function exists"
else
    echo "   ❌ apply_text_overlays() function missing"
    ((errors++))
fi

if grep -q "def auto_generate_overlays_from_recipe" backend/app/services/text_overlay.py; then
    echo "   ✅ auto_generate_overlays_from_recipe() function exists"
else
    echo "   ❌ auto_generate_overlays_from_recipe() function missing"
    ((errors++))
fi

if grep -q "def _build_drawtext_filter" backend/app/services/text_overlay.py; then
    echo "   ✅ _build_drawtext_filter() function exists"
else
    echo "   ❌ _build_drawtext_filter() function missing"
    ((errors++))
fi

# 7. Check style presets
echo ""
echo "7️⃣ Checking style presets..."
if grep -q "bold-white" backend/app/services/text_overlay.py; then
    echo "   ✅ bold-white style implemented"
else
    echo "   ❌ bold-white style missing"
    ((errors++))
fi

if grep -q "subtitle-bar" backend/app/services/text_overlay.py; then
    echo "   ✅ subtitle-bar style implemented"
else
    echo "   ❌ subtitle-bar style missing"
    ((errors++))
fi

if grep -q "minimal" backend/app/services/text_overlay.py; then
    echo "   ✅ minimal style implemented"
else
    echo "   ❌ minimal style missing"
    ((errors++))
fi

# 8. Check documentation
echo ""
echo "8️⃣ Checking documentation..."
if [ -f "TASK-005-BACKEND-SUMMARY.md" ]; then
    echo "   ✅ TASK-005-BACKEND-SUMMARY.md exists"
else
    echo "   ❌ Summary document missing"
    ((errors++))
fi

if grep -q "Task 005" AGENT-STATE.md; then
    echo "   ✅ AGENT-STATE.md updated"
else
    echo "   ❌ AGENT-STATE.md not updated"
    ((errors++))
fi

# 9. Check font paths
echo ""
echo "9️⃣ Checking font files..."
if [ -f "/System/Library/Fonts/Helvetica.ttc" ]; then
    echo "   ✅ Helvetica.ttc found"
else
    echo "   ⚠️  Helvetica.ttc not found (will use fallback)"
fi

if [ -f "/System/Library/Fonts/SFNS.ttf" ]; then
    echo "   ✅ SFNS.ttf found"
else
    echo "   ⚠️  SFNS.ttf not found (will use system default)"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $errors -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED!"
    echo ""
    echo "Backend implementation is complete and ready."
    echo "Next step: Frontend UI implementation"
else
    echo "❌ FAILED: $errors error(s) found"
    echo ""
    echo "Please review the errors above."
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
