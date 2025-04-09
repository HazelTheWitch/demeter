main() {
    pacman -Sy --noconfirm git uv
    git clone https://github.com/HazelTheWitch/demeter.git
    cd demeter
    uv run main.py
}

main
