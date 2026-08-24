import { getAWSCredentials } from "../api/axiosClient";

// Interface pour les credentials complets (utilisée lors de la création/validation)
export interface AWSCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  region: string;
}

// Interface pour les credentials retournés par l'API (sans secretAccessKey pour sécurité)
export interface AWSCredentialsResponse {
  configured: boolean;
  region?: string;
}

/**
 * Get AWS credentials from API (database only - no localStorage fallback)
 */
export const getStoredAWSCredentials =
  async (): Promise<AWSCredentialsResponse | null> => {
    try {
      // Get from API/database only
      const credentials = await getAWSCredentials();

      // Nouveau format: { configured: boolean, ... }
      if (!credentials || credentials.configured === false) {
        return null;
      }
      return credentials;
    } catch (error) {
      console.error(" Error fetching AWS credentials from API:", error);
      return null;
    }
  };

/**
 * Check if AWS credentials are available
 */
export const hasAWSCredentials = async (
  skipNetwork = false,
): Promise<boolean> => {
  // OK Pendant un audit, skip les appels réseau
  if (skipNetwork) {
    console.log(
      "[awsCredentialsHelper] skipNetwork=true, assume credentials OK",
    );
    return true;
  }

  try {
    const credentials = await getStoredAWSCredentials();
    const hasValidCredentials = !!(
      credentials?.configured && credentials?.region
    );
    return hasValidCredentials;
  } catch (error) {
    console.error(" Error checking AWS credentials:", error);
    return false;
  }
};

/**
 * Get AWS credentials for use in chat messages (with decrypted secret)
 */
export const getAWSCredentialsForChat = async (): Promise<string | null> => {
  return null;
};
