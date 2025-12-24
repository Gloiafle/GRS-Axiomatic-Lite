import random

def harvest_gift_energy():
    """Simple harvest loop for a single Geo-Monolith anchor."""
    capacity_mj = 0
    print("Monolith Status: ACTIVE. Harvesting Ionospheric Potential...")
    
    # Simulating the induction of atmospheric static
    for hour in range(24):
        hourly_yield = random.uniform(200, 500) # MJ of energy
        capacity_mj += hourly_yield
        print(f"Hour {hour}: +{hourly_yield:.2f} MJ harvested.")
        
    print(f"Total Daily Gift: {capacity_mj:.2f} MJ (Approx. 10 homes powered).")

if __name__ == "__main__":
    harvest_gift_energy()
