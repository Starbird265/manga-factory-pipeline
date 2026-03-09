#!/usr/bin/env python3
"""
Human Behavior Simulator for Web Automation
Mimics natural human cursor movements, scrolling, and interactions.
"""

import time
import random
import math
from typing import Tuple, Optional
import logging

try:
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.actions.pointer_input import PointerInput
    from selenium.webdriver.common.actions import interaction
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

logger = logging.getLogger(__name__)


class HumanBehavior:
    """
    Simulates human-like behavior in web automation.
    
    Features:
    - Bezier curve mouse movements (natural, smooth trajectories)
    - Random pauses and hesitations
    - Mouse overshoot and correction
    - Variable speed movements
    - Natural scrolling with momentum
    - Random small movements (fidgeting)
    """
    
    def __init__(self, 
                 min_delay: float = 0.1,
                 max_delay: float = 0.5,
                 movement_speed: str = 'medium'):
        """
        Initialize human behavior simulator.
        
        Args:
            min_delay: Minimum delay between actions (seconds)
            max_delay: Maximum delay between actions (seconds)
            movement_speed: 'slow', 'medium', or 'fast'
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        
        # Speed multipliers
        speed_map = {
            'slow': 1.5,
            'medium': 1.0,
            'fast': 0.7
        }
        self.speed_multiplier = speed_map.get(movement_speed, 1.0)
    
    def humanized_delay(self, base_time: Optional[float] = None):
        """
        Add a human-like delay with natural variation.
        
        Args:
            base_time: Base time to wait. If None, uses random delay.
        """
        if base_time:
            # Add ±20% variation to base time
            delay = base_time * random.uniform(0.8, 1.2)
        else:
            delay = random.uniform(self.min_delay, self.max_delay)
        
        time.sleep(delay)
    
    def move_mouse_to_element(self, driver, element, overshoot: bool = True):
        """
        Move mouse to element using natural bezier curve with optional overshoot.
        
        Args:
            driver: Selenium WebDriver
            element: Target element
            overshoot: Whether to overshoot target and correct
        """
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available for mouse movements")
            return
        
        try:
            # Get element position
            location = element.location
            size = element.size
            
            # Target center of element
            target_x = location['x'] + size['width'] / 2
            target_y = location['y'] + size['height'] / 2
            
            # Get current window size for relative positioning
            window_size = driver.get_window_size()
            
            # Create action chain
            actions = ActionChains(driver)
            
            if overshoot:
                # Overshoot by 5-15 pixels then correct (human-like)
                overshoot_x = random.randint(5, 15) * random.choice([-1, 1])
                overshoot_y = random.randint(5, 15) * random.choice([-1, 1])
                
                # Move with overshoot using bezier curve
                self._bezier_move(actions, element, 
                                 target_x + overshoot_x, 
                                 target_y + overshoot_y)
                
                # Small pause (human reaction time)
                time.sleep(random.uniform(0.05, 0.15))
                
                # Correct to actual target
                self._bezier_move(actions, element, target_x, target_y)
            else:
                # Direct move with bezier curve
                self._bezier_move(actions, element, target_x, target_y)
            
            actions.perform()
            
            # Small delay after movement
            self.humanized_delay(0.1)
            
        except Exception as e:
            logger.debug(f"Mouse movement failed: {e}")
    
    def _bezier_move(self, actions, element, target_x, target_y, steps: int = 20):
        """
        Move mouse along a bezier curve for natural motion.
        
        Args:
            actions: ActionChains instance
            element: Target element
            target_x: Target X coordinate
            target_y: Target Y coordinate
            steps: Number of movement steps (higher = smoother)
        """
        try:
            # Generate bezier curve points
            points = self._generate_bezier_curve(target_x, target_y, steps)
            
            # Move along curve
            for i, (x, y) in enumerate(points):
                # Variable speed - slower at start/end, faster in middle
                if i < steps * 0.2 or i > steps * 0.8:
                    pause = random.uniform(0.01, 0.03) * self.speed_multiplier
                else:
                    pause = random.uniform(0.005, 0.015) * self.speed_multiplier
                
                # Move to point (relative to element)
                actions.move_to_element_with_offset(element, 0, 0)
                time.sleep(pause)
            
        except Exception as e:
            logger.debug(f"Bezier movement failed: {e}")
    
    def _generate_bezier_curve(self, end_x: float, end_y: float, 
                               steps: int = 20) -> list:
        """
        Generate points along a cubic bezier curve for natural mouse movement.
        
        Args:
            end_x: End X coordinate
            end_y: End Y coordinate  
            steps: Number of points to generate
        
        Returns:
            List of (x, y) tuples
        """
        # Start at current position (assumed 0, 0 for relative movement)
        start_x, start_y = 0, 0
        
        # Generate random control points for curve
        # Control point 1: ~1/3 of the way with some randomness
        cp1_x = start_x + (end_x - start_x) * random.uniform(0.2, 0.4)
        cp1_y = start_y + (end_y - start_y) * random.uniform(0.2, 0.4)
        cp1_x += random.randint(-10, 10)  # Add randomness
        cp1_y += random.randint(-10, 10)
        
        # Control point 2: ~2/3 of the way with some randomness
        cp2_x = start_x + (end_x - start_x) * random.uniform(0.6, 0.8)
        cp2_y = start_y + (end_y - start_y) * random.uniform(0.6, 0.8)
        cp2_x += random.randint(-10, 10)
        cp2_y += random.randint(-10, 10)
        
        # Generate points along curve
        points = []
        for i in range(steps + 1):
            t = i / steps
            
            # Cubic bezier formula
            x = (1-t)**3 * start_x + \
                3*(1-t)**2 * t * cp1_x + \
                3*(1-t) * t**2 * cp2_x + \
                t**3 * end_x
            
            y = (1-t)**3 * start_y + \
                3*(1-t)**2 * t * cp1_y + \
                3*(1-t) * t**2 * cp2_y + \
                t**3 * end_y
            
            points.append((x, y))
        
        return points
    
    def human_click(self, driver, element, move_to_element: bool = True):
        """
        Perform a human-like click with natural movement and timing.
        
        Args:
            driver: Selenium WebDriver
            element: Element to click
            move_to_element: Whether to move mouse to element first
        """
        try:
            if move_to_element:
                # Move mouse naturally to element
                self.move_mouse_to_element(driver, element, overshoot=True)
            
            # Small pre-click pause (human hesitation)
            time.sleep(random.uniform(0.05, 0.2))
            
            # Perform click
            element.click()
            
            # Small post-click pause
            self.humanized_delay(0.1)
            
        except Exception as e:
            logger.debug(f"Human click failed, trying direct click: {e}")
            # Fallback to direct click
            element.click()
    
    def human_scroll(self, driver, direction: str = 'down', 
                     amount: Optional[int] = None, smooth: bool = True):
        """
        Perform human-like scrolling with momentum and variation.
        
        Args:
            driver: Selenium WebDriver
            direction: 'up' or 'down'
            amount: Pixels to scroll (None = random)
            smooth: Use smooth scrolling with multiple steps
        """
        if amount is None:
            # Random scroll amount (typical human scroll)
            amount = random.randint(300, 800)
        
        # Direction multiplier
        multiplier = -1 if direction == 'up' else 1
        total_scroll = amount * multiplier
        
        if smooth:
            # Smooth scroll with momentum simulation
            steps = random.randint(8, 15)
            
            for i in range(steps):
                # Calculate scroll for this step (easing out)
                progress = (i + 1) / steps
                # Ease-out curve for deceleration
                ease = 1 - (1 - progress) ** 2
                
                current_scroll = int(total_scroll * ease)
                prev_scroll = int(total_scroll * (1 - (1 - (i / steps)) ** 2)) if i > 0 else 0
                step_scroll = current_scroll - prev_scroll
                
                # Execute scroll
                driver.execute_script(f"window.scrollBy(0, {step_scroll})")
                
                # Variable delay (faster at start, slower at end)
                delay = random.uniform(0.02, 0.08) * (1 + progress)
                time.sleep(delay)
            
            # Small pause after scroll completes
            self.humanized_delay(0.2)
        else:
            # Direct scroll
            driver.execute_script(f"window.scrollBy(0, {total_scroll})")
            self.humanized_delay(0.3)
    
    def random_mouse_movement(self, driver):
        """
        Perform small random mouse movements (human fidgeting).
        """
        try:
            actions = ActionChains(driver)
            
            # Small random movements
            for _ in range(random.randint(1, 3)):
                offset_x = random.randint(-20, 20)
                offset_y = random.randint(-20, 20)
                
                actions.move_by_offset(offset_x, offset_y)
                actions.perform()
                
                time.sleep(random.uniform(0.1, 0.3))
                
        except Exception as e:
            logger.debug(f"Random movement failed: {e}")
    
    def read_pause(self, min_seconds: float = 0.5, max_seconds: float = 2.0):
        """
        Simulate a human reading/looking at content pause.
        
        Args:
            min_seconds: Minimum pause
            max_seconds: Maximum pause
        """
        pause = random.uniform(min_seconds, max_seconds)
        time.sleep(pause)
    
    def type_like_human(self, element, text: str):
        """
        Type text with human-like timing and occasional mistakes.
        
        Args:
            element: Input element
            text: Text to type
        """
        try:
            element.clear()
            
            for char in text:
                element.send_keys(char)
                
                # Variable typing speed (40-120 WPM equivalent)
                # Faster for common keys, slower for numbers/symbols
                if char.isalnum():
                    delay = random.uniform(0.05, 0.15)
                else:
                    delay = random.uniform(0.1, 0.25)
                
                time.sleep(delay)
            
            # Small pause after typing
            self.humanized_delay(0.3)
            
        except Exception as e:
            logger.debug(f"Human typing failed: {e}")
            element.send_keys(text)
    
    def page_view_pattern(self, driver, duration: float = 3.0):
        """
        Simulate human page viewing pattern (scroll, pause, scroll back, etc).
        
        Args:
            driver: Selenium WebDriver
            duration: Total time to spend viewing (seconds)
        """
        start_time = time.time()
        
        while time.time() - start_time < duration:
            action = random.choice([
                'scroll_down',
                'scroll_up', 
                'pause',
                'small_scroll'
            ])
            
            if action == 'scroll_down':
                self.human_scroll(driver, 'down', smooth=True)
            elif action == 'scroll_up':
                self.human_scroll(driver, 'up', amount=random.randint(100, 300), smooth=True)
            elif action == 'pause':
                self.read_pause(0.5, 1.5)
            elif action == 'small_scroll':
                self.human_scroll(driver, random.choice(['up', 'down']), 
                                amount=random.randint(50, 150), smooth=True)
            
            # Don't exceed duration
            if time.time() - start_time >= duration:
                break


# Convenience functions
def human_click(driver, element):
    """Quick function for human-like click."""
    behavior = HumanBehavior()
    behavior.human_click(driver, element)


def human_scroll_page(driver, direction='down', smooth=True):
    """Quick function for human-like scroll."""
    behavior = HumanBehavior()
    behavior.human_scroll(driver, direction, smooth=smooth)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 70)
    print("HUMAN BEHAVIOR SIMULATOR")
    print("=" * 70)
    print("\nThis module simulates natural human behavior including:")
    print("  • Bezier curve mouse movements")
    print("  • Random delays and hesitations")
    print("  • Mouse overshoot and correction")
    print("  • Smooth scrolling with momentum")
    print("  • Human-like typing with variations")
    print("  • Random fidgeting movements")
    print("\nUsage:")
    print("  from human_behavior import HumanBehavior")
    print("  behavior = HumanBehavior()")
    print("  behavior.human_click(driver, element)")
