# Entry point para geração de picks.
# Nota: O comportamento de reset automático do histórico foi removido.
# Agora os novos picks são anexados ao picks_history.csv sem duplicados.

from main import main

if __name__ == "__main__":
    main()
