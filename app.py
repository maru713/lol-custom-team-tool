import streamlit as st
import pandas as pd
import random
from itertools import combinations, permutations
import gspread
from google.oauth2.service_account import Credentials

ROLES = ["Top", "Jungle", "Mid", "ADC", "Support"]
RANK_TIERS = ["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond", "Master", "Grandmaster", "Challenger"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

gcp_secrets = st.secrets["gcp_service_account"]  # ← secrets.toml or cloud secrets
creds_dict = dict(gcp_secrets)
creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

# シートを開く（タイトル名で指定）
sheet = client.open("LoL_Custom_Teams").sheet1
if "confirmed_teams" not in st.session_state:
    st.session_state.confirmed_teams = None
def load_players_from_sheet():
    raw_rows = sheet.get_all_records()
    players = []
    for row in raw_rows:
        player = {"name": row["name"], "role_priorities": {}, "ranks": {}}
        for role in ROLES:
            player["role_priorities"][role] = row.get(f"{role}_priority", 0)
            tier = row.get(f"{role}_tier", "Silver")
            division = row.get(f"{role}_division", 4)
            player["ranks"][role] = {"tier": tier, "division": division}
        players.append(player)
    return players

def save_players_to_sheet(players):
    header = ["name"] + [f"{role}_priority" for role in ROLES] + [f"{role}_tier" for role in ROLES] + [f"{role}_division" for role in ROLES]
    values = [header]
    for p in players:
        row = [p["name"]]
        for role in ROLES:
            row.append(p["role_priorities"].get(role, 0))
        for role in ROLES:
            rank = p["ranks"].get(role, {})
            row.append(rank.get("tier", "Silver"))
        for role in ROLES:
            row.append(rank.get("division", 4))
        values.append(row)
    
    sheet.clear()
    sheet.update("A1", values)

st.set_page_config(page_title="LoLカスタムチーム分け", layout="wide")

# ティア＋ディビジョンをスコアに変換（Iron4 = 0, Iron1 = 3, Bronze4 = 4, ..., Challenger = 39）
def get_adjusted_rank_score(tier, division, name):
    base_score = get_rank_score(tier, division)
    win_data = st.session_state.player_wins.get(name, {"win": 0, "total": 0})
    win = win_data["win"]
    total = win_data["total"]

    if total == 0:
        return base_score  # 試合数が0なら補正しない

    win_rate = win / total
    adjustment = (win_rate - 0.5) * 8  # 補正係数 8 は調整可
    return base_score + adjustment

if st.button("スプレッドシートから再読み込み"):
    st.session_state.players_data = load_players_from_sheet()
    st.success("データを再読み込みしました")

def get_initial_players():
    names = [f"Player{i+1}" for i in range(10)]
    players = []
    for name in names:
        player = {"name": name, "role_priorities": {}, "ranks": {}}
        for role in ROLES:
            priority = random.choices([-1, 0, 1, 2, 3, 4], weights=[1, 2, 2, 2, 2, 2])[0]
            # ここでランクをEmerald以下に制限
            limited_tiers = RANK_TIERS[:6 + 1]  # Iron〜Emerald（インデックス0〜6）
            tier = random.choice(limited_tiers)
            div = random.randint(1, 4) if tier in RANK_TIERS[:7] else None
            player["role_priorities"][role] = priority
            player["ranks"][role] = {"tier": tier, "division": div}
        players.append(player)
    return players
# 最初にプレイヤーリストを初期化
# 初期化: 勝敗データ
if "player_wins" not in st.session_state:
    st.session_state.player_wins = {}
# 初期化: プレイヤーデータ
if "players_data" not in st.session_state:
    st.session_state.players_data = []
if st.button("デバッグ用：10人ランダム追加"):
    new_players = get_initial_players()
    st.session_state.players_data.extend(new_players)
    for p in new_players:
        # 勝率情報もダミーで埋めておく
        wins = random.randint(0, 10)
        total = random.randint(wins + 1, wins + 10)
        st.session_state.player_wins[p["name"]] = {"win": wins, "total": total}
    st.success("ランダムな10人のプレイヤーを追加しました。")
    save_players_to_sheet(st.session_state.players_data)

st.title("LoLカスタムチーム分けツール")

# プレイヤー選択
player_options = ["新規プレイヤー追加"] + [p["name"] for p in st.session_state.players_data]
selected_player = st.selectbox("プレイヤーを選択", options=player_options)

# プレイヤー編集・追加画面
if selected_player == "新規プレイヤー追加":
    player_data = {
        "name": "",
        "role_priorities": {role: 0 for role in ROLES},
        "ranks": {role: {"tier": "Silver", "division": 4} for role in ROLES},
        "win": 0,
        "loss": 0
    }
    mode = "add"
else:
    player_data = next(p for p in st.session_state.players_data if p["name"] == selected_player)
    mode = "edit"

# 入力フォーム
player_data["name"] = st.text_input("名前", value=player_data["name"])
for role in ROLES:
    player_data["role_priorities"][role] = st.selectbox(
        f"{role}の希望度", [-1, 0, 1, 2, 3, 4], index=[-1, 0, 1, 2, 3, 4].index(player_data["role_priorities"].get(role, 0))
    )
    tier = st.selectbox(f"{role}のティア", RANK_TIERS, index=RANK_TIERS.index(player_data["ranks"][role]["tier"]))
    division = None
    if tier in RANK_TIERS[:7]:
        division = st.number_input(f"{role}のディビジョン", 1, 4, value=player_data["ranks"][role].get("division", 4), step=1)
    player_data["ranks"][role] = {"tier": tier, "division": division}

# 保存ボタン
if st.button("保存"):
    if mode == "add":
        st.session_state.players_data.append(player_data)
        st.success(f"{player_data['name']} を追加しました")
        save_players_to_sheet(st.session_state.players_data)

    else:
        for i, p in enumerate(st.session_state.players_data):
            if p["name"] == selected_player:
                st.session_state.players_data[i] = player_data
                st.success(f"{player_data['name']} を更新しました")
                save_players_to_sheet(st.session_state.players_data)
                break



st.title("LoLカスタムチーム分けツール")
st.markdown("### チーム分け対象選択（10人）")
player_names = [p['name'] or f"プレイヤー{i+1}" for i, p in enumerate(st.session_state.players_data)]
selected_names = st.multiselect("対象プレイヤーを10人選択", options=player_names, default=player_names[:10])

if len(selected_names) != 10:
    st.warning("ちょうど10人選択してください")
st.markdown("### プレイヤー編集")

# ロールとランク希望をもとにペア差分評価
def assign_roles(team):
    best_assignment = None
    best_score = -float("inf")
    for perm in permutations(team, 5):
        score = 0
        valid = True
        for p, role in zip(perm, ROLES):
            if p['role_priorities'][role] == -1:
                valid = False
                break
            score += p['role_priorities'][role]
        if valid and score > best_score:
            best_assignment = list(zip(perm, ROLES))
            best_score = score
    return best_assignment

def matchup_gap(assign1, assign2):
    total_gap = 0
    for (p1, role), (p2, _) in zip(assign1, assign2):
        r1 = get_adjusted_rank_score(
            p1['ranks'][role]['tier'],
            p1['ranks'][role]['division'],
            p1['name']
        )

        r2 = get_adjusted_rank_score(
            p2['ranks'][role]['tier'],
            p2['ranks'][role]['division'],
            p2['name']
        )

        gap = abs(r1 - r2)
        penalized = gap ** 2 if gap >= 2 else gap  # ★ここでペナルティ強化
        total_gap += penalized
    return total_gap


def find_best_balance(players):
    best_pair = None
    min_gap = float("inf")
    for comb in combinations(players, 5):
        t1 = list(comb)
        t2 = [p for p in players if p not in t1]
        a1 = assign_roles(t1)
        a2 = assign_roles(t2)
        if a1 and a2:
            gap = matchup_gap(a1, a2)
            if gap < min_gap:
                min_gap = gap
                best_pair = (a1, a2)
    return best_pair

def get_rank_score(tier, division):
    if tier in RANK_TIERS[:7]:  # Iron〜Diamond
        tier_index = RANK_TIERS.index(tier)
        return tier_index * 4 + (4 - division)
    else:  # Master〜Challenger
        return 28 + (RANK_TIERS.index(tier) - 6)

def average_matchup_gap(assign1, assign2):
    diffs = []
    for (p1, role), (p2, _) in zip(assign1, assign2):
        r1 = get_adjusted_rank_score(
            tier=p1['ranks'][role]['tier'],
            division=p1['ranks'][role]['division'],
            name=p1['name']
        )
        r2 = get_adjusted_rank_score(
            tier=p2['ranks'][role]['tier'],
            division=p2['ranks'][role]['division'],
            name=p2['name']
        )
        gap = abs(r1 - r2)
        diffs.append(gap)
    return sum(diffs) / len(diffs)


def optimize_matchup_gap(team1, team2):
    best_t1 = team1[:]
    best_t2 = team2[:]
    best_gap = average_matchup_gap(best_t1, best_t2)
    improved = True

    while improved:
        improved = False
        for i in range(len(ROLES)):
            (p1, role1) = best_t1[i]
            for j in range(len(ROLES)):
                (p2, role2) = best_t2[j]
                if role1 != role2:
                    continue
                # スワップ試行
                new_t1 = best_t1[:]
                new_t2 = best_t2[:]
                new_t1[i] = (p2, role1)
                new_t2[j] = (p1, role2)
                new_gap = average_matchup_gap(new_t1, new_t2)
                if new_gap < best_gap:
                    best_gap = new_gap
                    best_t1 = new_t1
                    best_t2 = new_t2
                    improved = True
                    break  # 改善があったので次ループへ
            if improved:
                break

    return best_t1, best_t2, best_gap


def format_player_label(p, role):
    rank = p['ranks'][role]
    label = f"{p['name']}（{role} / {rank['tier']}"
    if rank['division']:
        label += f"{rank['division']}"
    label += ")"
    
    # 勝率を付加
    win_data = st.session_state.player_wins.get(p["name"], {"win": 0, "total": 0})
    if win_data["total"] > 0:
        wr = win_data["win"] / win_data["total"]
        label += f"　勝率: {wr:.0%}"
    else:
        label += "　勝率: N/A"
    return label
if st.session_state.get("confirmed_teams") and st.session_state.get("last_teams"):
    st.markdown("### ✅ チーム確定済み")

    winner = st.radio("勝ったチームは？", options=["🟥 チーム1", "🟦 チーム2"], key="winner_select")
    if st.button("結果を記録"):
        t1, t2 = st.session_state.get("confirmed_teams", ([], []))
        if winner == "🟥 チーム1":
            winners, losers = t1, t2
        else:
            winners, losers = t2, t1

        for p, _ in winners:
            name = p["name"]
            if name not in st.session_state.player_wins:
                st.session_state.player_wins[name] = {"win": 0, "total": 0}
            st.session_state.player_wins[name]["win"] += 1
            st.session_state.player_wins[name]["total"] += 1

        for p, _ in losers:
            name = p["name"]
            if name not in st.session_state.player_wins:
                st.session_state.player_wins[name] = {"win": 0, "total": 0}
            st.session_state.player_wins[name]["total"] += 1

        st.success(f"{winner} の勝利を記録しました")
        st.session_state.confirmed_teams = None  # リセット
elif st.session_state.get("last_teams"):
    if st.button("チームを確定"):
        st.session_state.confirmed_teams = st.session_state.get("last_teams", None)
        st.success("このチーム構成を確定しました")
if len(selected_names) == 10 and st.button("チーム分け実行"):
    selected_players = [p for p in st.session_state.players_data if p['name'] in selected_names]
    result = find_best_balance(selected_players)
    if result:
        t1, t2 = result
        t1, t2, matchup_gap = optimize_matchup_gap(t1, t2)
        st.session_state.last_teams = (t1, t2)

        st.markdown("### 🟥 チーム1")
        for p, role in t1:
            st.write(format_player_label(p, role))

        st.markdown("### 🟦 チーム2")
        for p, role in t2:
            st.write(format_player_label(p, role))

        st.success("ロールとランクのバランスを最も近づけたチーム分けを表示しています。")

        team1_score = sum(get_adjusted_rank_score(**p['ranks'][role], name=p['name']) for p, role in t1)
        team2_score = sum(get_adjusted_rank_score(**p['ranks'][role], name=p['name']) for p, role in t2)

        matchup_gap = average_matchup_gap(t1, t2)

        st.markdown("## チームスコア比較（参考）")
        col1, col2 = st.columns(2)
        col1.metric("🟥 チーム1 総合ランク", team1_score)
        col2.metric("🟦 チーム2 総合ランク", team2_score)

        st.markdown(f"### 平均ティア差（対面ごと）: `{matchup_gap:.2f}`")

    else:
        st.error("有効なロール割り当てが見つかりませんでした。")
