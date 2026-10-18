"""Serial genuine startup and three corrected identity/owner profiles."""
from scripts.capture_barnet2018_runtime_20261017 import main as capture
from scripts.publish_barrow2017_owned_transaction_20261017 import FOLDER,RELEASE

TAG='owned_opening_2017_18_r146a_20261017'
PROFILES=((10987,'moore','Moore'),(10989,'dunne','Dunne'),(9592,'hornby','Hornby'))


if __name__=='__main__':
    capture(folder=FOLDER,season='2017-18',release_id=RELEASE,tag=TAG,profiles=PROFILES)
