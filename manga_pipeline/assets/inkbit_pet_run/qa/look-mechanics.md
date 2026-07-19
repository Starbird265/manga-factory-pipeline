# Inkbit Look Mechanics

Inkbit is a rounded ink-body sprite with a stable lower body, a page-tab rising from its top, an attached pointer on its screen-left side, and a small amber attachment on its screen-right side. Its practical attention cue is the combination of amber eyes, short head/body lean, page-tab angle, and pointer placement.

The lower body and feet remain anchored. Eyes lead the attention change, then the upper body leans subtly in the same direction. The page-tab follows that lean by a smaller amount. The pointer stays attached and traces a short arc with the body; the amber side attachment stays rigidly attached. The whole sprite must never rotate or skew as a single object.

Cardinal poses:

- `000` up: pupils and brows lift, page-tab leans slightly back, upper body rises a little while the feet remain planted.
- `090` screen-right: pupils, face, and upper body turn toward screen-right; the amber attachment becomes slightly more visible and the pointer is partly occluded by the body.
- `180` down: pupils and eyelids aim toward the lower body/page area; the page-tab tips forward and the upper body compresses gently.
- `270` screen-left: pupils, face, and upper body turn toward screen-left; the pointer becomes more visible and the amber attachment is partly occluded.

The diagonal poses interpolate those mechanics in even steps. Keep Inkbit's scale, baseline, silhouette, scarf, outline, palette, and attachment positions coherent across the complete clockwise loop.
