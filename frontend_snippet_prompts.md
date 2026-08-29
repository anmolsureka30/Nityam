## Integrate the <Strands /> component from React Bits

You are helping integrate an open-source React component into an existing application.

### Component: Strands
### Variant: JavaScript + CSS
### Dependencies: ogl

---

### Usage Example
```jsx
import Strands from './Strands';

<div style={{ width: '100%', height: '600px', position: 'relative' }}>
  <Strands
    colors={["#F97316","#7C3AED","#06B6D4"]}
    count={3}
    speed={0.5}
    amplitude={1}
    waviness={1}
    thickness={0.7}
    glow={2.6}
    taper={3}
    spread={1}
    intensity={0.6}
    saturation={1.5}
    opacity={1}
    scale={1.5}
    glass={false}
    refraction={1}
    dispersion={1}
    glassSize={1}
  />
</div>
```

### Props
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| colors | string[] | ["#FF4242", "#7C3AED", "#06B6D4", "#EAB308"] | Palette of hex colors cycled across the strands. Pass an empty array to use the built-in rainbow spectrum. |
| count | number | 3 | Number of strands woven through the animation. |
| speed | number | 0.5 | How quickly the strands ripple and flow. |
| amplitude | number | 1 | Vertical reach of each strand as it waves up and down. |
| waviness | number | 1 | Density of the curves along each strand. |
| thickness | number | 0.7 | Width of each glowing strand. |
| glow | number | 2.6 | Strength of the luminous bloom around the strands. |
| taper | number | 3 | How sharply the strands fade out toward the edges. |
| spread | number | 1 | Separation between strands so they fan out instead of overlapping. |
| hueShift | number | 0 | Rotates the colors around the strands for variation. |
| intensity | number | 0.6 | Overall brightness and energy of the effect. |
| saturation | number | 1 | Vibrance of the colors. Above 1 makes them more intense, below 1 fades to grayscale. |
| opacity | number | 1 | Overall transparency of the rendered strands. |
| scale | number | 1 | Zooms the whole effect in or out to make the strands bigger or smaller. |
| glass | boolean | false | Renders the strands inside a refractive glass ball. |
| refraction | number | 1 | How strongly the glass ball bends the light passing through it. |
| dispersion | number | 1 | Amount of rainbow color separation along the edges of the glass ball. |
| glassSize | number | 1 | Size of the glass ball relative to the canvas. |

### Full Component Source
```jsx
import { Renderer, Program, Mesh, Color, Triangle, RenderTarget } from 'ogl';
import { useEffect, useRef } from 'react';

import './Strands.css';

const MAX_STRANDS = 12;
const MAX_COLORS = 8;

const VERT = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const FRAG = `#version 300 es
precision highp float;

uniform float uTime;
uniform vec2 uResolution;
uniform vec3 uColors[${MAX_COLORS}];
uniform int uColorCount;
uniform int uStrandCount;
uniform float uSpeed;
uniform float uAmplitude;
uniform float uWaviness;
uniform float uThickness;
uniform float uGlow;
uniform float uTaper;
uniform float uSpread;
uniform float uHueShift;
uniform float uIntensity;
uniform float uOpacity;
uniform float uScale;
uniform float uSaturation;

out vec4 fragColor;

const float PI = 3.14159265;

vec3 spectrum(float t) {
  return 0.5 + 0.5 * cos(2.0 * PI * (t + vec3(0.00, 0.33, 0.67)));
}

vec3 samplePalette(float t) {
  t = fract(t);
  float scaled = t * float(uColorCount);
  int idx = int(floor(scaled));
  float blend = fract(scaled);
  int nextIdx = idx + 1;
  if (nextIdx >= uColorCount) nextIdx = 0;
  return mix(uColors[idx], uColors[nextIdx], blend);
}

vec3 strandColor(float t) {
  if (uColorCount > 0) return samplePalette(t);
  return spectrum(t);
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
  uv /= max(uScale, 0.0001);

  float e = 0.06 + uIntensity * 0.94;
  float env = pow(max(cos(uv.x * PI * 1.3), 0.0), uTaper);

  vec3 col = vec3(0.0);

  for (int i = 0; i < ${MAX_STRANDS}; i++) {
    if (i >= uStrandCount) break;

    float fi = float(i);
    float ph = fi * 1.7 * uSpread;
    float freq = (2.0 + fi * 0.35) * uWaviness;
    float spd = 1.4 + fi * 1.2;

    float tt = uTime * uSpeed;
    float w = sin(uv.x * freq + tt * spd + ph) * 0.60
            + sin(uv.x * freq * 1.1 - tt * spd * 0.7 + ph * 1.7) * 0.40;

    float amp = (0.1 + 0.02 * e) * env * uAmplitude;
    float y = w * amp;

    float d = abs(uv.y - y);
    float thick = (0.001 + 0.05 * e) * (0.35 + env) * uThickness;
    float g = thick / (d + thick * 0.45);
    g = g * g;

    float h = fi / float(uStrandCount) + uv.x * 0.30 + uTime * 0.04 + uHueShift;
    col += strandColor(h) * g * env;
  }

  col *= 0.45 + 0.7 * e;
  col = 1.0 - exp(-col * uGlow);

  float gray = dot(col, vec3(0.2126, 0.7152, 0.0722));
  col = max(mix(vec3(gray), col, uSaturation), 0.0);

  float lum = max(max(col.r, col.g), col.b);
  float alpha = clamp(lum, 0.0, 1.0) * uOpacity;

  fragColor = vec4(col * uOpacity, alpha);
}
`;

const GLASS_FRAG = `#version 300 es
precision highp float;

uniform sampler2D uScene;
uniform vec2 uResolution;
uniform float uRadius;
uniform float uRefraction;
uniform float uDispersion;

out vec4 fragColor;

vec2 toUv(vec2 p) {
  return p * (uResolution.y / uResolution) + 0.5;
}

void main() {
  vec2 p = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
  float d = length(p);
  float r = uRadius;

  float edge = fwidth(d) * 1.5;
  float mask = 1.0 - smoothstep(r - edge, r + edge, d);
  if (mask <= 0.0) {
    fragColor = vec4(0.0);
    return;
  }

  // sphere height: 0 at the rim, 1 at the center
  float z = sqrt(max(r * r - d * d, 0.0)) / r;
  float nd = d / r; // 0 at the center, 1 at the rim

  // refraction is confined to a narrow band near the rim; the rest stays undistorted
  vec2 dir = d > 0.0 ? p / d : vec2(0.0);
  float lens = smoothstep(0.85, 1.0, nd) * pow(nd, 6.0);
  vec2 offset = -dir * lens * uRefraction * 0.15;
  vec2 disp = -dir * lens * uDispersion * 0.012;

  vec3 light;
  light.r = texture(uScene, toUv(p + offset - disp)).r;
  light.g = texture(uScene, toUv(p + offset)).g;
  light.b = texture(uScene, toUv(p + offset + disp)).b;

  // neutral fresnel rim (no color tint so the glass stays clear)
  float fres = pow(1.0 - z, 3.0);
  vec3 rim = vec3(1.0) * fres * 0.18;

  // specular highlight from the upper-left
  vec2 lightDir = normalize(vec2(-0.55, 0.6));
  float spec = pow(max(dot(p / max(r, 1e-4), lightDir), 0.0), 6.0);
  spec *= smoothstep(r, r * 0.55, d);

  vec3 emissive = light + rim + vec3(spec) * 0.4;
  float emissiveA = clamp(max(max(emissive.r, emissive.g), emissive.b), 0.0, 1.0);

  // almost clear glass body: only a faint neutral darkening, mostly near the rim
  float bodyA = 0.05 + fres * 0.05;

  // composite emissive light over the clear body (premultiplied)
  float outA = emissiveA + bodyA * (1.0 - emissiveA);
  vec3 outRGB = emissive;

  outRGB *= mask;
  outA *= mask;

  fragColor = vec4(outRGB, outA);
}
`;

const buildPalette = colors => {
  const filled = colors && colors.length ? colors : ['#ffffff'];
  const padded = [];
  for (let i = 0; i < MAX_COLORS; i++) {
    const hex = filled[i] ?? filled[filled.length - 1];
    const c = new Color(hex);
    padded.push([c.r, c.g, c.b]);
  }
  return padded;
};

export default function Strands({
  colors = ['#FF4242', '#7C3AED', '#06B6D4', '#EAB308'],
  count = 3,
  speed = 0.5,
  amplitude = 1,
  waviness = 1,
  thickness = 0.7,
  glow = 2.6,
  taper = 3,
  spread = 1,
  hueShift = 0,
  intensity = 0.6,
  saturation = 1.5,
  opacity = 1,
  scale = 1.5,
  glass = false,
  refraction = 1,
  dispersion = 1,
  glassSize = 1,
  className = '',
  style
}) {
  const propsRef = useRef({});
  propsRef.current = {
    colors,
    count,
    speed,
    amplitude,
    waviness,
    thickness,
    glow,
    taper,
    spread,
    hueShift,
    intensity,
    saturation,
    opacity,
    scale,
    glass,
    refraction,
    dispersion,
    glassSize
  };

  const ctnDom = useRef(null);

  useEffect(() => {
    const ctn = ctnDom.current;
    if (!ctn) return;

    const renderer = new Renderer({
      alpha: true,
      premultipliedAlpha: true,
      antialias: true
    });
    const gl = renderer.gl;
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.canvas.style.backgroundColor = 'transparent';

    const geometry = new Triangle(gl);
    if (geometry.attributes.uv) {
      delete geometry.attributes.uv;
    }

    const program = new Program(gl, {
      vertex: VERT,
      fragment: FRAG,
      uniforms: {
        uTime: { value: 0 },
        uResolution: { value: [ctn.offsetWidth, ctn.offsetHeight] },
        uColors: { value: buildPalette(propsRef.current.colors) },
        uColorCount: { value: Math.min(propsRef.current.colors.length, MAX_COLORS) },
        uStrandCount: { value: Math.min(propsRef.current.count, MAX_STRANDS) },
        uSpeed: { value: speed },
        uAmplitude: { value: amplitude },
        uWaviness: { value: waviness },
        uThickness: { value: thickness },
        uGlow: { value: glow },
        uTaper: { value: taper },
        uSpread: { value: spread },
        uHueShift: { value: hueShift },
        uIntensity: { value: intensity },
        uOpacity: { value: opacity },
        uScale: { value: scale },
        uSaturation: { value: saturation }
      }
    });

    const mesh = new Mesh(gl, { geometry, program });

    const renderTarget = new RenderTarget(gl, {
      width: ctn.offsetWidth,
      height: ctn.offsetHeight
    });

    const glassProgram = new Program(gl, {
      vertex: VERT,
      fragment: GLASS_FRAG,
      uniforms: {
        uScene: { value: renderTarget.texture },
        uResolution: { value: [ctn.offsetWidth, ctn.offsetHeight] },
        uRadius: { value: 0.46 * glassSize },
        uRefraction: { value: refraction },
        uDispersion: { value: dispersion }
      }
    });
    const glassMesh = new Mesh(gl, { geometry, program: glassProgram });

    ctn.appendChild(gl.canvas);

    function resize() {
      if (!ctn) return;
      const width = ctn.offsetWidth;
      const height = ctn.offsetHeight;
      renderer.setSize(width, height);
      program.uniforms.uResolution.value = [width, height];
      renderTarget.setSize(width, height);
      glassProgram.uniforms.uResolution.value = [width, height];
    }
    window.addEventListener('resize', resize);
    resize();

    let animateId = 0;
    const update = t => {
      animateId = requestAnimationFrame(update);
      const current = propsRef.current;
      program.uniforms.uTime.value = t * 0.001;
      program.uniforms.uColors.value = buildPalette(current.colors);
      program.uniforms.uColorCount.value = Math.min(current.colors.length, MAX_COLORS);
      program.uniforms.uStrandCount.value = Math.min(Math.max(Math.round(current.count), 1), MAX_STRANDS);
      program.uniforms.uSpeed.value = current.speed;
      program.uniforms.uAmplitude.value = current.amplitude;
      program.uniforms.uWaviness.value = current.waviness;
      program.uniforms.uThickness.value = current.thickness;
      program.uniforms.uGlow.value = current.glow;
      program.uniforms.uTaper.value = current.taper;
      program.uniforms.uSpread.value = current.spread;
      program.uniforms.uHueShift.value = current.hueShift;
      program.uniforms.uIntensity.value = current.intensity;
      program.uniforms.uOpacity.value = current.opacity;
      program.uniforms.uScale.value = current.scale;
      program.uniforms.uSaturation.value = current.saturation;

      if (current.glass) {
        renderer.render({ scene: mesh, target: renderTarget });
        glassProgram.uniforms.uScene.value = renderTarget.texture;
        glassProgram.uniforms.uRefraction.value = current.refraction;
        glassProgram.uniforms.uDispersion.value = current.dispersion;
        glassProgram.uniforms.uRadius.value = 0.46 * current.glassSize;
        renderer.render({ scene: glassMesh });
      } else {
        renderer.render({ scene: mesh });
      }
    };
    animateId = requestAnimationFrame(update);

    return () => {
      cancelAnimationFrame(animateId);
      window.removeEventListener('resize', resize);
      if (ctn && gl.canvas.parentNode === ctn) {
        ctn.removeChild(gl.canvas);
      }
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={ctnDom} className={`strands-container ${className}`} style={style} />;
}

```

### Component CSS
```css
.strands-container {
  position: relative;
  width: 100%;
  height: 100%;
  background: transparent;
}

.strands-container canvas {
  display: block;
  width: 100%;
  height: 100%;
}

```

### Integration Instructions
1. Install any listed dependencies.
2. Copy the component source into the appropriate directory in the project.
3. Import the CSS file alongside the component.
4. Import and render the component using the usage example above as a starting point.
5. Adjust props as needed for the specific use case — refer to the props table for all available options.

### More from React Bits
The full library index, including everything reactbits.dev offers, is at https://reactbits.dev/llms.txt — fetch it if this component is not the right fit or the project needs more pieces.


## Integrate the <CardNav /> component from React Bits

You are helping integrate an open-source React component into an existing application.

### Component: CardNav
### Variant: JavaScript + CSS
### Dependencies: gsap

---

### Usage Example
```jsx
import CardNav from './CardNav'
import logo from './logo.svg';

const App = () => {
  const items = [
    {
      label: "About",
      bgColor: "#1B1722",
      textColor: "#fff",
      links: [
        { label: "Company", ariaLabel: "About Company" },
        { label: "Careers", ariaLabel: "About Careers" }
      ]
    },
    {
      label: "Projects", 
      bgColor: "#2F293A",
      textColor: "#fff",
      links: [
        { label: "Featured", ariaLabel: "Featured Projects" },
        { label: "Case Studies", ariaLabel: "Project Case Studies" }
      ]
    },
    {
      label: "Contact",
      bgColor: "#2F293A", 
      textColor: "#fff",
      links: [
        { label: "Email", ariaLabel: "Email us" },
        { label: "Twitter", ariaLabel: "Twitter" },
        { label: "LinkedIn", ariaLabel: "LinkedIn" }
      ]
    }
  ];

  return (
    <CardNav
      logo={logo}
      logoAlt="Company Logo"
      items={items}
      baseColor="#fff"
      menuColor="#000"
      buttonBgColor="#111"
      buttonTextColor="#fff"
      ease="power3.out"
    />
  );
};
```

### Props
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| logo | string | - | URL for the logo image |
| logoAlt | string | Logo | Alt text for the logo image |
| items | CardNavItem[] | - | Array of navigation items with label, bgColor, textColor, and links |
| className | string | '' | Additional CSS classes for the navigation container |
| ease | string | power3.out | GSAP easing function for animations |
| baseColor | string | #fff | Background color for the navigation container |
| menuColor | string | undefined | Color for the hamburger menu lines |
| buttonBgColor | string | #111 | Background color for the CTA button |
| buttonTextColor | string | white | Text color for the CTA button |

### Full Component Source
```jsx
import { useLayoutEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
// use your own icon import if react-icons is not available
import { GoArrowUpRight } from 'react-icons/go';
import './CardNav.css';

const CardNav = ({
  logo,
  logoAlt = 'Logo',
  items,
  className = '',
  ease = 'power3.out',
  baseColor = '#fff',
  menuColor,
  buttonBgColor,
  buttonTextColor
}) => {
  const [isHamburgerOpen, setIsHamburgerOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const navRef = useRef(null);
  const cardsRef = useRef([]);
  const tlRef = useRef(null);

  const calculateHeight = () => {
    const navEl = navRef.current;
    if (!navEl) return 260;

    const isMobile = window.matchMedia('(max-width: 768px)').matches;
    if (isMobile) {
      const contentEl = navEl.querySelector('.card-nav-content');
      if (contentEl) {
        const wasVisible = contentEl.style.visibility;
        const wasPointerEvents = contentEl.style.pointerEvents;
        const wasPosition = contentEl.style.position;
        const wasHeight = contentEl.style.height;

        contentEl.style.visibility = 'visible';
        contentEl.style.pointerEvents = 'auto';
        contentEl.style.position = 'static';
        contentEl.style.height = 'auto';

        contentEl.offsetHeight;

        const topBar = 60;
        const padding = 16;
        const contentHeight = contentEl.scrollHeight;

        contentEl.style.visibility = wasVisible;
        contentEl.style.pointerEvents = wasPointerEvents;
        contentEl.style.position = wasPosition;
        contentEl.style.height = wasHeight;

        return topBar + contentHeight + padding;
      }
    }
    return 260;
  };

  const createTimeline = () => {
    const navEl = navRef.current;
    if (!navEl) return null;

    gsap.set(navEl, { height: 60, overflow: 'hidden' });
    gsap.set(cardsRef.current, { y: 50, opacity: 0 });

    const tl = gsap.timeline({ paused: true });

    tl.to(navEl, {
      height: calculateHeight,
      duration: 0.4,
      ease
    });

    tl.to(cardsRef.current, { y: 0, opacity: 1, duration: 0.4, ease, stagger: 0.08 }, '-=0.1');

    return tl;
  };

  useLayoutEffect(() => {
    const tl = createTimeline();
    tlRef.current = tl;

    return () => {
      tl?.kill();
      tlRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ease, items]);

  useLayoutEffect(() => {
    const handleResize = () => {
      if (!tlRef.current) return;

      if (isExpanded) {
        const newHeight = calculateHeight();
        gsap.set(navRef.current, { height: newHeight });

        tlRef.current.kill();
        const newTl = createTimeline();
        if (newTl) {
          newTl.progress(1);
          tlRef.current = newTl;
        }
      } else {
        tlRef.current.kill();
        const newTl = createTimeline();
        if (newTl) {
          tlRef.current = newTl;
        }
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isExpanded]);

  const toggleMenu = () => {
    const tl = tlRef.current;
    if (!tl) return;
    if (!isExpanded) {
      setIsHamburgerOpen(true);
      setIsExpanded(true);
      tl.play(0);
    } else {
      setIsHamburgerOpen(false);
      tl.eventCallback('onReverseComplete', () => setIsExpanded(false));
      tl.reverse();
    }
  };

  const setCardRef = i => el => {
    if (el) cardsRef.current[i] = el;
  };

  return (
    <div className={`card-nav-container ${className}`}>
      <nav ref={navRef} className={`card-nav ${isExpanded ? 'open' : ''}`} style={{ backgroundColor: baseColor }}>
        <div className="card-nav-top">
          <div
            className={`hamburger-menu ${isHamburgerOpen ? 'open' : ''}`}
            onClick={toggleMenu}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleMenu();
              }
            }}
            role="button"
            aria-label={isExpanded ? 'Close menu' : 'Open menu'}
            aria-expanded={isExpanded}
            tabIndex={0}
            style={{ color: menuColor || '#000' }}
          >
            <div className="hamburger-line" />
            <div className="hamburger-line" />
          </div>

          <div className="logo-container">
            <img src={logo} alt={logoAlt} className="logo" />
          </div>

          <button
            type="button"
            className="card-nav-cta-button"
            style={{ backgroundColor: buttonBgColor, color: buttonTextColor }}
          >
            Get Started
          </button>
        </div>

        <div className="card-nav-content" aria-hidden={!isExpanded}>
          {(items || []).slice(0, 3).map((item, idx) => (
            <div
              key={`${item.label}-${idx}`}
              className="nav-card"
              ref={setCardRef(idx)}
              style={{ backgroundColor: item.bgColor, color: item.textColor }}
            >
              <div className="nav-card-label">{item.label}</div>
              <div className="nav-card-links">
                {item.links?.map((lnk, i) => (
                  <a key={`${lnk.label}-${i}`} className="nav-card-link" href={lnk.href} aria-label={lnk.ariaLabel}>
                    <GoArrowUpRight className="nav-card-link-icon" aria-hidden="true" />
                    {lnk.label}
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      </nav>
    </div>
  );
};

export default CardNav;

```

### Component CSS
```css
.card-nav-container {
  position: absolute;
  top: 2em;
  left: 50%;
  transform: translateX(-50%);
  width: 90%;
  max-width: 800px;
  z-index: 99;
  box-sizing: border-box;
}

.card-nav {
  display: block;
  height: 60px;
  padding: 0;
  background-color: white;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.75rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  position: relative;
  overflow: hidden;
  will-change: height;
}

.card-nav-top {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.45rem 0.55rem 1.1rem;
  z-index: 2;
}

.hamburger-menu {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  gap: 6px;
}

.hamburger-menu:hover .hamburger-line {
  opacity: 0.75;
}

.hamburger-line {
  width: 30px;
  height: 2px;
  background-color: currentColor;
  transition:
    transform 0.25s ease,
    opacity 0.2s ease,
    margin 0.3s ease;
  transform-origin: 50% 50%;
}

.hamburger-menu.open .hamburger-line:first-child {
  transform: translateY(4px) rotate(45deg);
}

.hamburger-menu.open .hamburger-line:last-child {
  transform: translateY(-4px) rotate(-45deg);
}

.logo-container {
  display: flex;
  align-items: center;
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
}

.logo {
  height: 28px;
}

.card-nav-cta-button {
  background-color: #111;
  color: white;
  border: none;
  border-radius: calc(0.75rem - 0.35rem);
  padding: 0 1rem;
  height: 100%;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.3s ease;
  align-items: center;
}

.card-nav-cta-button:hover {
  background-color: #333;
}

.card-nav-content {
  position: absolute;
  left: 0;
  right: 0;
  top: 60px;
  bottom: 0;
  padding: 0.5rem;
  display: flex;
  align-items: flex-end;
  gap: 12px;
  visibility: hidden;
  pointer-events: none;
  z-index: 1;
}

.card-nav.open .card-nav-content {
  visibility: visible;
  pointer-events: auto;
}

.nav-card {
  height: 100%;
  flex: 1 1 0;
  min-width: 0;
  border-radius: calc(0.75rem - 0.2rem);
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  gap: 8px;
  user-select: none;
}

.nav-card-label {
  font-weight: 400;
  font-size: 22px;
  letter-spacing: -0.5px;
}

.nav-card-links {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-card-link {
  font-size: 16px;
  cursor: pointer;
  text-decoration: none;
  transition: opacity 0.3s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.nav-card-link:hover {
  opacity: 0.75;
}

@media (max-width: 768px) {
  .card-nav-container {
    width: 90%;
    top: 1.2em;
  }

  .card-nav-top {
    padding: 0.5rem 1rem;
    justify-content: space-between;
  }

  .hamburger-menu {
    order: 2;
  }

  .logo-container {
    position: static;
    transform: none;
    order: 1;
  }

  .card-nav-cta-button {
    display: none;
  }

  .card-nav-content {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
    padding: 0.5rem;
    bottom: 0;
    justify-content: flex-start;
  }

  .nav-card {
    height: auto;
    min-height: 60px;
    flex: 1 1 auto;
    max-height: none;
  }

  .nav-card-label {
    font-size: 18px;
  }

  .nav-card-link {
    font-size: 15px;
  }
}

```

### Integration Instructions
1. Install any listed dependencies.
2. Copy the component source into the appropriate directory in the project.
3. Import the CSS file alongside the component.
4. Import and render the component using the usage example above as a starting point.
5. Adjust props as needed for the specific use case — refer to the props table for all available options.

### More from React Bits
The full library index, including everything reactbits.dev offers, is at https://reactbits.dev/llms.txt — fetch it if this component is not the right fit or the project needs more pieces.


Add the "Mosaic Waves" component from React Bits Pro to my project.

Waves rolling through a mosaic of shifting tiles

Steps:
1. Ensure my components.json has the React Bits Pro registries configured (see https://pro.reactbits.dev/docs/installation), including the Authorization header with my REACTBITS_LICENSE_KEY environment variable.
2. Install the component with:
   npx shadcn@latest add @reactbits-starter/mosaic-waves-tw
3. Import it where needed and adapt it to my project's content and design tokens.

Docs page for reference: https://pro.reactbits.dev/docs/components/mosaic-waves


Add the "Gradient Carousel" component from React Bits Pro to my project.

3D card carousel with dynamic gradient background extraction

Steps:
1. Ensure my components.json has the React Bits Pro registries configured (see https://pro.reactbits.dev/docs/installation), including the Authorization header with my REACTBITS_LICENSE_KEY environment variable.
2. Install the component with:
   npx shadcn@latest add @reactbits-starter/gradient-carousel-tw
3. Import it where needed and adapt it to my project's content and design tokens.

Docs page for reference: https://pro.reactbits.dev/docs/components/gradient-carousel

# Sidebar
URL: /docs/components/radix/sidebar

***

title: Sidebar
description: A composable, themeable and customizable sidebar component. Created by Shadcn and animated by Animate UI.
author:
name: imskyleen
url: [https://github.com/imskyleen](https://github.com/imskyleen)
-----------------------------------------------------------------

<ComponentPreview name="demo-components-radix-sidebar" iframe bigScreen />

## Installation

<ComponentInstallation name="components-radix-sidebar" />

## Usage

```tsx
<SidebarProvider>
  <Sidebar>
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>Item 1</SidebarMenuItem>
        <SidebarMenuItem>Item 2</SidebarMenuItem>
        <SidebarMenuItem>Item 3</SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>
    <SidebarContent>
      <SidebarGroup>
        <SidebarGroupLabel>Label 1</SidebarGroupLabel>
        <SidebarMenu>
          <SidebarMenuItem>Item 1</SidebarMenuItem>
          <SidebarMenuItem>Item 2</SidebarMenuItem>
          <SidebarMenuItem>Item 3</SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
      <SidebarGroup>
        <SidebarGroupLabel>Label 2</SidebarGroupLabel>
        <SidebarMenu>
          <SidebarMenuItem>Item 1</SidebarMenuItem>
          <SidebarMenuItem>Item 2</SidebarMenuItem>
          <SidebarMenuItem>Item 3</SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter>
      <SidebarMenu>
        <SidebarMenuItem>Item 1</SidebarMenuItem>
        <SidebarMenuItem>Item 2</SidebarMenuItem>
        <SidebarMenuItem>Item 3</SidebarMenuItem>
      </SidebarMenu>
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
  <SidebarInset>
    <SidebarTrigger />
    {...}
  </SidebarInset>
</SidebarProvider>
```

## API Reference

### SidebarProvider

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebarprovider" text="Shadcn UI API Reference - SidebarProvider" />
</div>

### Sidebar

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebar" text="Shadcn UI API Reference - Sidebar" />
</div>

### useSidebar

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#usesidebar" text="Shadcn UI API Reference - useSidebar" />
</div>

### SidebarHeader

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebarheader" text="Shadcn UI API Reference - SidebarHeader" />
</div>

### SidebarFooter

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebarfooter" text="Shadcn UI API Reference - SidebarFooter" />
</div>

### SidebarContent

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebarcontent" text="Shadcn UI API Reference - SidebarContent" />
</div>

### SidebarGroup

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebargroup" text="Shadcn UI API Reference - SidebarGroup" />
</div>

### Collapsible SidebarGroup

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#collapsible-sidebargroup" text="Shadcn UI API Reference - Collapsible SidebarGroup" />
</div>

### SidebarGroupAction

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebargroupaction" text="Shadcn UI API Reference - SidebarGroupAction" />
</div>

### SidebarMenu

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebarmenu" text="Shadcn UI API Reference - SidebarMenu" />
</div>

### SidebarMenuButton

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidemenubutton" text="Shadcn UI API Reference - SidebarMenuButton" />
</div>

### SidebarMenuAction

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidemenuaction" text="Shadcn UI API Reference - SidebarMenuAction" />
</div>

### SidebarMenuSub

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidemenusub" text="Shadcn UI API Reference - SidebarMenuSub" />
</div>

### Collapsible SidebarMenu

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#collapsible-sidemenusub" text="Shadcn UI API Reference - Collapsible SidebarMenuSub" />
</div>

### SidebarMenuBadge

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidemenubadge" text="Shadcn UI API Reference - SidebarMenuBadge" />
</div>

### SidebarMenuSkeleton

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidemenuskeleton" text="Shadcn UI API Reference - SidebarMenuSkeleton" />
</div>

### SidebarSeparator

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidemenu" text="Shadcn UI API Reference - SidebarMenu" />
</div>

### SidebarTrigger

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidetrigger" text="Shadcn UI API Reference - SidebarTrigger" />
</div>

### SidebarRail

<div className="flex flex-col gap-2">
  <ExternalLink href="https://ui.shadcn.com/docs/components/sidebar#sidebarrail" text="Shadcn UI API Reference - SidebarRail" />
</div>

## Credits

* Credit to [shadcn/ui](https://ui.shadcn.com/docs/components/sidebar) for the sidebar component.


# Hexagon Background
URL: /docs/components/backgrounds/hexagon

***

title: Hexagon Background
description: A background component featuring an interactive hexagon grid.
author:
name: imskyleen
url: [https://github.com/imskyleen](https://github.com/imskyleen)
-----------------------------------------------------------------

<ComponentPreview name="demo-components-backgrounds-hexagon" />

## Installation

<ComponentInstallation name="components-backgrounds-hexagon" />

## Usage

```tsx
<HexagonBackground />
```

## API Reference

### HexagonBackground

<TypeTable
  type={{
  hexagonSize: {
    description: 'The size of the hexagon.',
    type: 'number',
    required: false,
    default: '75',
  },
  hexagonMargin: {
    description: 'The margin of the hexagon.',
    type: 'number',
    required: false,
    default: '3',
  },
  hexagonProps: {
    description: 'The props for the hexagon.',
    type: 'React.ComponentProps<"div">',
    required: false,
  },
  '...props': {
    description: 'The props of the GradientBackground.',
    type: 'React.ComponentProps<"div">',
    required: false,
  },
}}
/>

## Credits

* Credits to [Denis Klak](https://codepen.io/d3nis031/pen/QWyeNYx) for the inspiration


"use client";
import { cn } from "@/lib/utils";
import { CanvasText } from "@/components/ui/canvas-text";

export function CanvasTextDemo() {
  return (
    <div className="flex min-h-80 items-center justify-center p-8">
      <h2
        className={cn(
          "group relative mx-auto mt-4 max-w-2xl text-left text-4xl leading-20 font-bold tracking-tight text-balance text-neutral-600 sm:text-5xl md:text-6xl xl:text-7xl dark:text-neutral-700",
        )}
      >
        Ship landing pages at{" "}
        <CanvasText
          text="Lightning Speed"
          backgroundClassName="bg-blue-600 dark:bg-blue-700"
          colors={[
            "rgba(0, 153, 255, 1)",
            "rgba(0, 153, 255, 0.9)",
            "rgba(0, 153, 255, 0.8)",
            "rgba(0, 153, 255, 0.7)",
            "rgba(0, 153, 255, 0.6)",
            "rgba(0, 153, 255, 0.5)",
            "rgba(0, 153, 255, 0.4)",
            "rgba(0, 153, 255, 0.3)",
            "rgba(0, 153, 255, 0.2)",
            "rgba(0, 153, 255, 0.1)",
          ]}
          lineGap={4}
          animationDuration={20}
        />
      </h2>
    </div>
  );
}

import { CalendarIcon, FileTextIcon } from "@radix-ui/react-icons"
import { BellIcon, Share2Icon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Calendar } from "@/components/ui/calendar"
import AnimatedBeamMultipleOutputDemo from "@/registry/example/animated-beam-multiple-outputs"
import AnimatedListDemo from "@/registry/example/animated-list-demo"
import { BentoCard, BentoGrid } from "@/registry/magicui/bento-grid"
import { Marquee } from "@/registry/magicui/marquee"

const files = [
  {
    name: "bitcoin.pdf",
    body: "Bitcoin is a cryptocurrency invented in 2008 by an unknown person or group of people using the name Satoshi Nakamoto.",
  },
  {
    name: "finances.xlsx",
    body: "A spreadsheet or worksheet is a file made of rows and columns that help sort data, arrange data easily, and calculate numerical data.",
  },
  {
    name: "logo.svg",
    body: "Scalable Vector Graphics is an Extensible Markup Language-based vector image format for two-dimensional graphics with support for interactivity and animation.",
  },
  {
    name: "keys.gpg",
    body: "GPG keys are used to encrypt and decrypt email, files, directories, and whole disk partitions and to authenticate messages.",
  },
  {
    name: "seed.txt",
    body: "A seed phrase, seed recovery phrase or backup seed phrase is a list of words which store all the information needed to recover Bitcoin funds on-chain.",
  },
]

const features = [
  {
    Icon: FileTextIcon,
    name: "Save your files",
    description: "We automatically save your files as you type.",
    href: "#",
    cta: "Learn more",
    className: "col-span-3 lg:col-span-1",
    background: (
      <Marquee
        pauseOnHover
        className="absolute top-10 [mask-image:linear-gradient(to_top,transparent_40%,#000_100%)] [--duration:20s]"
      >
        {files.map((f, idx) => (
          <figure
            key={idx}
            className={cn(
              "relative w-32 cursor-pointer overflow-hidden rounded-xl border p-4",
              "border-gray-950/[.1] bg-gray-950/[.01] hover:bg-gray-950/[.05]",
              "dark:border-gray-50/[.1] dark:bg-gray-50/[.10] dark:hover:bg-gray-50/[.15]",
              "transform-gpu blur-[1px] transition-all duration-300 ease-out hover:blur-none"
            )}
          >
            <div className="flex flex-row items-center gap-2">
              <div className="flex flex-col">
                <figcaption className="text-sm font-medium dark:text-white">
                  {f.name}
                </figcaption>
              </div>
            </div>
            <blockquote className="mt-2 text-xs">{f.body}</blockquote>
          </figure>
        ))}
      </Marquee>
    ),
  },
  {
    Icon: BellIcon,
    name: "Notifications",
    description: "Get notified when something happens.",
    href: "#",
    cta: "Learn more",
    className: "col-span-3 lg:col-span-2",
    background: (
      <AnimatedListDemo className="absolute top-4 right-2 h-[300px] w-full scale-75 border-none [mask-image:linear-gradient(to_top,transparent_10%,#000_100%)] transition-all duration-300 ease-out group-hover:scale-90" />
    ),
  },
  {
    Icon: Share2Icon,
    name: "Integrations",
    description: "Supports 100+ integrations and counting.",
    href: "#",
    cta: "Learn more",
    className: "col-span-3 lg:col-span-2",
    background: (
      <AnimatedBeamMultipleOutputDemo className="absolute top-4 right-2 h-[300px] border-none [mask-image:linear-gradient(to_top,transparent_10%,#000_100%)] transition-all duration-300 ease-out group-hover:scale-105" />
    ),
  },
  {
    Icon: CalendarIcon,
    name: "Calendar",
    description: "Use the calendar to filter your files by date.",
    className: "col-span-3 lg:col-span-1",
    href: "#",
    cta: "Learn more",
    background: (
      <Calendar
        mode="single"
        selected={new Date(2022, 4, 11, 0, 0, 0)}
        className="absolute top-10 right-0 origin-top scale-75 rounded-md border [mask-image:linear-gradient(to_top,transparent_40%,#000_100%)] transition-all duration-300 ease-out group-hover:scale-90"
      />
    ),
  },
]

export function BentoDemo() {
  return (
    <BentoGrid>
      {features.map((feature, idx) => (
        <BentoCard key={idx} {...feature} />
      ))}
    </BentoGrid>
  )
}


import { HeroVideoDialog } from "@/registry/magicui/hero-video-dialog"

export function HeroVideoDialogDemo() {
  return (
    <div className="relative">
      <HeroVideoDialog
        className="block dark:hidden"
        animationStyle="from-center"
        videoSrc="https://www.youtube.com/embed/qh3NGpYRG3I?si=4rb-zSdDkVK9qxxb"
        thumbnailSrc="https://startup-template-sage.vercel.app/hero-light.png"
        thumbnailAlt="Hero Video"
      />
      <HeroVideoDialog
        className="hidden dark:block"
        animationStyle="from-center"
        videoSrc="https://www.youtube.com/embed/qh3NGpYRG3I?si=4rb-zSdDkVK9qxxb"
        thumbnailSrc="https://startup-template-sage.vercel.app/hero-dark.png"
        thumbnailAlt="Hero Video"
      />
    </div>
  )
}

"use client"

import { cn } from "@/lib/utils"
import { NoiseTexture } from "@/registry/magicui/noise-texture"

export function NoiseTextureDemo() {
  return (
    <div className="relative flex h-[500px] w-full flex-col items-center justify-center overflow-hidden rounded-lg border bg-neutral-100/80 dark:bg-neutral-950">
      <NoiseTexture
        className={cn(
          "absolute inset-0",
          "mask-[radial-gradient(420px_circle_at_center,white,transparent)]"
        )}
      />
    </div>
  )
}


"use client"

import { useEffect, useState } from "react"

import { AnimatedCircularProgressBar } from "@/registry/magicui/animated-circular-progress-bar"

export function AnimatedCircularProgressBarDemo() {
  const [value, setValue] = useState(0)

  useEffect(() => {
    const handleIncrement = (prev: number) => {
      if (prev === 100) {
        return 0
      }
      return prev + 10
    }
    setValue(handleIncrement)
    const interval = setInterval(() => setValue(handleIncrement), 2000)
    return () => clearInterval(interval)
  }, [])

  return (
    <AnimatedCircularProgressBar
      value={value}
      gaugePrimaryColor="rgb(79 70 229)"
      gaugeSecondaryColor="rgba(0, 0, 0, 0.1)"
    />
  )
}


import { ComicText } from "@/registry/magicui/comic-text"

export function ComicTextDemo() {
  return (
    <div className="space-y-8 text-center">
      <ComicText fontSize={5}>BOOM!</ComicText>
    </div>
  )
}


