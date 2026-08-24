//  src/components/Chat/ProviderSelector.tsx

import { Button, Stack, Typography } from "@mui/material";

export interface ProviderSelectorProps {
  onProviderSelected: (providerType: string | null) => void;
}

export default function ProviderSelector({ onProviderSelected }: ProviderSelectorProps) {
  return (
    <Stack spacing={2}>
      <Typography variant="h6" color="white">
         Choisissez un fournisseur cloud
      </Typography>
      <Button variant="contained" onClick={() => onProviderSelected("aws")}>
        AWS
      </Button>
      <Button variant="contained" onClick={() => onProviderSelected("azure")}>
        Azure
      </Button>
      <Button variant="contained" onClick={() => onProviderSelected("gcp")}>
        GCP
      </Button>
    </Stack>
  );
}
