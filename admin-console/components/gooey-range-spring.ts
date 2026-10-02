// A damped spring keeps its velocity when a new range interrupts the motion.
export interface RangeSpring {
  from: number;
  velocity: number;
  target: number;
}

const decay = 24 / (2 * 0.9);
const frequency = Math.sqrt(220 / 0.9 - decay * decay);

export function sampleRangeSpring(spring: RangeSpring, seconds: number) {
  const displacement = spring.from - spring.target;
  const sineWeight = (spring.velocity + decay * displacement) / frequency;
  const sine = Math.sin(frequency * seconds);
  const cosine = Math.cos(frequency * seconds);
  const envelope = Math.exp(-decay * seconds);
  const wave = displacement * cosine + sineWeight * sine;
  return {
    position: spring.target + envelope * wave,
    velocity: envelope * (-decay * wave + frequency * (-displacement * sine + sineWeight * cosine)),
  };
}

export function retargetRangeSpring(
  spring: RangeSpring,
  seconds: number,
  target: number,
): RangeSpring {
  const current = sampleRangeSpring(spring, seconds);
  return { from: current.position, velocity: current.velocity, target };
}
