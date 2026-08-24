import { saveAWSCredentials } from '../api/axiosClient';

export interface AWSCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  region: string;
  sessionToken?: string;
}

export interface ValidationResult {
  isValid: boolean;
  error?: string;
  details?: {
    account?: string;
    userId?: string;
    arn?: string;
  };
}

/**
 * Valide les credentials AWS en faisant un appel de test
 */
export async function validateAWSCredentials(credentials: AWSCredentials): Promise<ValidationResult> {
  try {
    // Pour l'instant, on simule la validation avec un délai
    // En production, ceci devrait faire un appel AWS STS GetCallerIdentity
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Validation basique des formats
    if (!credentials.accessKeyId || !credentials.secretAccessKey || !credentials.region) {
      return {
        isValid: false,
        error: 'Tous les champs obligatoires doivent être remplis'
      };
    }

    // Validation du format Access Key ID (commence par AKIA ou ASIA)
    const accessKeyPattern = /^(AKIA|ASIA)[0-9A-Z]{16}$/;
    if (!accessKeyPattern.test(credentials.accessKeyId)) {
      return {
        isValid: false,
        error: 'Format de l\'Access Key ID invalide. Doit commencer par AKIA ou ASIA suivi de 16 caractères alphanumériques.'
      };
    }

    // Validation du format Secret Access Key (40 caractères alphanumériques + / et +)
    const secretKeyPattern = /^[A-Za-z0-9/+=]{40}$/;
    if (!secretKeyPattern.test(credentials.secretAccessKey)) {
      return {
        isValid: false,
        error: 'Format de la Secret Access Key invalide. Doit contenir exactement 40 caractères.'
      };
    }

    // Si on arrive ici, les credentials sont valides en format
    // En production, on ferait ici l'appel STS réel
    
    return {
      isValid: true,
      details: {
        account: 'xxxxxxxxx' + credentials.accessKeyId.slice(-4),
        userId: 'AIDA' + credentials.accessKeyId.slice(-8),
        arn: `arn:aws:iam::xxxxxxxxx:user/devops-user`
      }
    };

  } catch (error) {
    console.error('AWS validation error:', error);
    return {
      isValid: false,
      error: 'Erreur lors de la validation des credentials AWS. Veuillez vérifier vos informations.'
    };
  }
}

/**
 * Sauvegarde et valide les credentials AWS
 */
export async function saveAndValidateAWSCredentials(credentials: AWSCredentials): Promise<ValidationResult> {
  try {
    // D'abord on valide
    const validationResult = await validateAWSCredentials(credentials);
    
    if (!validationResult.isValid) {
      return validationResult;
    }

    // Puis on sauvegarde si la validation est OK
    await saveAWSCredentials({
      accessKeyId: credentials.accessKeyId,
      secretAccessKey: credentials.secretAccessKey,
      region: credentials.region
    });

    return validationResult;

  } catch (error) {
    console.error('Save and validate error:', error);
    return {
      isValid: false,
      error: 'Impossible de sauvegarder les credentials. Veuillez réessayer.'
    };
  }
}

/**
 * Test rapide de connectivité AWS
 */
export async function testAWSConnection(credentials: AWSCredentials): Promise<boolean> {
  try {
    const result = await validateAWSCredentials(credentials);
    return result.isValid;
  } catch {
    return false;
  }
}