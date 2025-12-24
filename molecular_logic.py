class CircRNAPayload:
    """
    PZR Delta-01: Biological Logic Simulation
    Simulates the boolean logic of the circRNA payload inside a cell.
    """
    def __init__(self, cell_type, activator_present=False):
        self.cell_type = cell_type
        self.activator_present = activator_present
        self.therapeutic_protein = "Anti-IgE ScFv (Omalizumab-Variant)"
        
        # Liver-specific microRNA marker (High in Hepatocytes)
        self.mir_122_high = True if cell_type == "Hepatocyte" else False

    def ribosome_scan(self):
        """
        The ribosome attempts to translate the circRNA.
        Logic: IF (Liver Cell) AND (Activator Key Present) -> EXPRESS
        """
        print(f"--- Scanning Cell: {self.cell_type} ---")
        
        # LOGIC GATE 1: Tissue Specificity (miRNA Sensor)
        if not self.mir_122_high:
            return "SILENCED: Off-target cell detected. Translation blocked."
        
        # LOGIC GATE 2: The 'Key' (Small Molecule Inducer)
        if not self.activator_present:
            return "DORMANT: Payload stable. Waiting for Activator Key."
            
        return self._express_protein()

    def _express_protein(self):
        return f"ACTIVE: Expressing {self.therapeutic_protein}. Neutralizing IgE..."

# --- SIMULATION ---

# Scenario A: Payload enters a lung cell (Off-target)
lung_cell = CircRNAPayload(cell_type="Lung_Epithelial", activator_present=True)
print(f"Scenario A: {lung_cell.ribosome_scan()}")

# Scenario B: Payload enters liver, but no Key (The Seed Phase)
liver_seed = CircRNAPayload(cell_type="Hepatocyte", activator_present=False)
print(f"Scenario B: {liver_seed.ribosome_scan()}")

# Scenario C: Payload enters liver + Key Administered (The Cure Phase)
liver_active = CircRNAPayload(cell_type="Hepatocyte", activator_present=True)
print(f"Scenario C: {liver_active.ribosome_scan()}")
