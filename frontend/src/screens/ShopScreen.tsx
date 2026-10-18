import React, { useState, useEffect, useCallback } from 'react';

const generateTxId = (): string => `iap_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
import { Zap, Video } from 'lucide-react';
import { ScreenId, ShopPack, Transaction } from '../models';
import { TopBar } from '../widgets/TopBar';
import { Button3D } from '../widgets/Button3D';
import {
  claimRewardedAdApi,
  fetchShopPacks,
  fetchTransactionHistory,
  mockInitialTransactions,
  mockShopPacks,
  verifyIapApi,
} from '../services/api';

export interface ShopScreenProps {
  tokensCount: number;
  onNavigate: (screen: ScreenId) => void;
  onAddTokens: (amount: number, title?: string) => void;
}

export const ShopScreen: React.FC<ShopScreenProps> = ({
  tokensCount,
  onNavigate,
  onAddTokens,
}) => {
  const [packs, setPacks] = useState<ShopPack[]>(mockShopPacks);
  const [transactions, setTransactions] = useState<Transaction[]>(mockInitialTransactions);
  const [isWatchingAd, setIsWatchingAd] = useState(false);
  const [_isLoadingPacks, setIsLoadingPacks] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function loadShop() {
      setIsLoadingPacks(true);
      try {
        const [loadedPacks, loadedTxs] = await Promise.all([
          fetchShopPacks(),
          fetchTransactionHistory(),
        ]);
        if (isMounted) {
          if (loadedPacks && loadedPacks.length > 0) setPacks(loadedPacks);
          if (loadedTxs && loadedTxs.length > 0) setTransactions(loadedTxs);
        }
      } catch {
        // keep fallback
      } finally {
        if (isMounted) setIsLoadingPacks(false);
      }
    }
    loadShop();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleBuyPack = useCallback(async (pack: ShopPack) => {
    const total = pack.tokens + (pack.bonusTokens || 0);
    const txId = generateTxId();
    try {
      await verifyIapApi(pack.sku || pack.id, txId);
      onAddTokens(total, `Achat Pack ${pack.tokens} Jetons (${pack.price})`);
      const updatedTxs = await fetchTransactionHistory();
      setTransactions(updatedTxs);
      alert(`🎉 Achat réussi ! Vous avez reçu ${total} Jetons.`);
    } catch (err: any) {
      // Priorité 3 : Suppression du contournement boutique. Aucun jeton n'est crédité en cas d'échec serveur.
      alert(`❌ Échec de l'achat : ${err.message || 'Paiement non vérifié par le serveur.'}`);
    }
  }, [onAddTokens]);

  const handleWatchAd = async () => {
    setIsWatchingAd(true);
    try {
      await new Promise((r) => setTimeout(r, 1500)); // simulate ad playback
      await claimRewardedAdApi();
      onAddTokens(1, 'Vidéo Publicitaire Récompensée');
      const updatedTxs = await fetchTransactionHistory();
      setTransactions(updatedTxs);
      alert('🎬 Vidéo terminée ! +1 Jeton gratuit crédité sur votre compte.');
    } catch (err: any) {
      // Priorité 3 : Suppression du contournement boutique. Aucun jeton n'est crédité en cas d'échec serveur.
      alert(`❌ Récompense non validée : ${err.message || 'La vérification serveur de la vidéo a échoué.'}`);
    } finally {
      setIsWatchingAd(false);
    }
  };

  return (
    <div style={{ paddingBottom: 30, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <TopBar
        title="Boutique de Jetons"
        showBack
        onBack={() => onNavigate('home')}
        tokensCount={tokensCount}
        onTokensClick={() => {}}
      />

      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        
        {/* Big Balance Hero Card */}
        <div
          style={{
            backgroundColor: '#312E81',
            borderRadius: 24,
            padding: '22px 20px',
            color: '#FFFFFF',
            border: '3px solid #1E1B4B',
            boxShadow: '0 6px 0 #1E1B4B',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <span style={{ fontSize: '11px', fontWeight: 800, color: '#C7D2FE', textTransform: 'uppercase' }}>
              Solde disponible
            </span>
            <div style={{ fontSize: '32px', fontWeight: 900, color: '#FCD34D', margin: '4px 0 2px' }}>
              ⚡ {tokensCount} Jetons
            </div>
            <p style={{ margin: 0, fontSize: '12px', color: '#E0E7FF', fontWeight: 600 }}>
              1 jeton = 1 génération de thème IA complet
            </p>
          </div>

          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 18,
              backgroundColor: '#F59E0B',
              boxShadow: '0 3px 0 #B45309',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#FFFFFF',
            }}
          >
            <Zap size={28} fill="#FFFFFF" />
          </div>
        </div>

        {/* Free Rewarded Ad Action */}
        <div
          style={{
            backgroundColor: '#ECFDF5',
            borderRadius: 20,
            border: '2px solid #10B981',
            boxShadow: '0 3px 0 #059669',
            padding: '16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: 14,
                backgroundColor: '#10B981',
                boxShadow: '0 2px 0 #047857',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#FFFFFF',
              }}
            >
              <Video size={22} />
            </div>
            <div>
              <div style={{ fontSize: '15px', fontWeight: 900, color: '#065F46' }}>
                Regarder une Vidéo
              </div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#047857' }}>
                Gagnez +1 Jeton gratuitement (15-30s)
              </div>
            </div>
          </div>

          <Button3D
            variant="success"
            size="sm"
            disabled={isWatchingAd}
            onClick={handleWatchAd}
          >
            {isWatchingAd ? 'Lecture...' : 'Regarder'}
          </Button3D>
        </div>

        {/* In-App Purchase Packs Grid */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <h3 style={{ fontSize: '17px', fontWeight: 900, color: '#1E1B4B', margin: 0 }}>
              Packs de Jetons
            </h3>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748B' }}>
              Paiement Sécurisé
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {packs.map((pack) => (
              <div
                key={pack.id}
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: 20,
                  padding: '16px 18px',
                  border: pack.isPopular ? '2px solid #F59E0B' : '2px solid #E2E8F0',
                  boxShadow: pack.isPopular ? '0 4px 0 #D97706' : '0 3px 0 #CBD5E1',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 14,
                      backgroundColor: pack.isPopular ? '#FEF3C7' : '#EEF2FF',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: pack.isPopular ? '#B45309' : '#4F46E5',
                      fontWeight: 900,
                      fontSize: '18px',
                    }}
                  >
                    ⚡
                  </div>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: '17px', fontWeight: 900, color: '#1E1B4B' }}>
                        {pack.tokens} Jetons
                      </span>
                      {pack.bonusTokens && (
                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: 900,
                            backgroundColor: '#D1FAE5',
                            color: '#065F46',
                            padding: '2px 6px',
                            borderRadius: 8,
                          }}
                        >
                          +{pack.bonusTokens} OFFERTS
                        </span>
                      )}
                    </div>
                    {pack.badge && (
                      <span style={{ fontSize: '11px', fontWeight: 800, color: '#F59E0B' }}>
                        ★ {pack.badge}
                      </span>
                    )}
                  </div>
                </div>

                <Button3D
                  variant={pack.isPopular ? 'primary' : 'neutral'}
                  size="md"
                  onClick={() => handleBuyPack(pack)}
                >
                  {pack.price}
                </Button3D>
              </div>
            ))}
          </div>
        </div>

        {/* Transactions History Table */}
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: 900, color: '#1E1B4B', margin: '0 0 10px' }}>
            Historique des Jetons
          </h3>
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 18,
              border: '2px solid #E2E8F0',
              boxShadow: '0 2px 0 #CBD5E1',
              padding: '6px 14px',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {transactions.map((t, idx) => (
              <div
                key={t.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 0',
                  borderBottom: idx !== transactions.length - 1 ? '1px solid #F1F5F9' : 'none',
                }}
              >
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#1E1B4B' }}>{t.title}</div>
                  <div style={{ fontSize: '11px', color: '#94A3B8', fontWeight: 600 }}>{t.date}</div>
                </div>
                <div
                  style={{
                    fontSize: '14px',
                    fontWeight: 900,
                    color: t.type === 'gain' ? '#10B981' : '#F43F5E',
                  }}
                >
                  {t.type === 'gain' ? `+${t.amount}` : t.amount} ⚡
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};
