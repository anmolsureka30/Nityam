/* Import order matters: the rig defines PARAMS, DESIGN and draw; the emotion
 * and speech engines build on those; mount uses all three. */
import { NS } from "./ns.js";
import "./rig.js";
import "./emotions.js";
import "./speech.js";
import "./mount.js";

export default NS;
