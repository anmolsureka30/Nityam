# Trajectory Equation Matching
`trajectory_equation_matching`


## Taught in shruti:a070d0331a_77f6cb3e @32:18
A reverse-engineering method to find a projectile's launch speed u and projection angle theta by comparing a given Cartesian trajectory equation to the standard projectile trajectory equation y = x*tan(theta) - g*x^2 / (2*u^2 * cos^2(theta)). In the lecture, the trajectory equation y = x - x^2 is matched coefficient-by-coefficient to find tan(theta) = 1 (giving theta = 45 degrees) and g / (2*u^2 * cos^2(theta)) = 1 (giving u = sqrt(10) m/s with g = 10 m/s^2). These parameters are then used to calculate the maximum height H = 0.25 meters and range R = 1 meter using standard kinematic formulas.
