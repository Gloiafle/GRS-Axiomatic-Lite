class PZRGift:
    def __init__(self, target_cell="Hepatocyte"):
        self.target = target_cell
        self.is_active = False

    def check_safety_gate(self, tissue_type):
        """Logic: Only activate if Tissue == Hepatocyte"""
        if tissue_type == self.target:
            self.is_active = True
            return "SAFETY_CLEAR: Initializing permanent allergy suppression."
        return "SAFETY_LOCK: Inactive in this tissue type."

# Example: Citizen takes the PZR Seed
gift = PZRGift()
print(gift.check_safety_gate("Hepatocyte"))
